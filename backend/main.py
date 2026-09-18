"""LexiSA API: lightweight contract intelligence for South African SMMEs."""
from __future__ import annotations

import json
import os
import re
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from enum import Enum
from pathlib import Path
from typing import Any

import fitz
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from database import count_records, get_chat_history, get_contract, init_db, load_rules_matrix, save_chat_message, save_contract
from middleware.cost_controller import CostControlMiddleware
from services.analyzer import analyze_clauses_with_gemini
from services.chat_rag import answer_contract_question
from services.parser import extract_text_from_file
from services.pdf_exporter import export_contract_pdf
from services.redliner import accept_redline, apply_redlines_to_clauses, list_redlines, submit_custom_redline
from services.segmenter import segment_clauses

load_dotenv()
try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover
    genai = None

app = FastAPI(title="LexiSA Contract Intelligence API", version="0.1.0")
# Added before CORSMiddleware so CORS ends up as the outermost layer (Starlette
# wraps middleware in reverse-registration order) and still decorates 429
# quota-exceeded responses.
app.add_middleware(CostControlMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:3002", "http://localhost:3003"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
RULES_MATRIX = load_rules_matrix()
init_db()

DEMO_CONTRACT = """MASTER SERVICES AGREEMENT

1. Services
The Supplier will provide software implementation, support and advisory services described in each Statement of Work.

2. Warranty
2.1 The Supplier warrants that the Services will materially conform to the Statement of Work for a period of 30 days from delivery.

3. Client Data
3.1 The Supplier may process personal information supplied by the Client in connection with the Services. The Supplier will use reasonable security measures and may appoint service providers to assist with processing.

4. Indemnity
4.1 The Supplier indemnifies, defends and holds harmless the Client and its affiliates from and against any and all claims, losses, damages, costs and expenses arising out of or relating to the Services, without limitation.

5. Intellectual Property
5.1 All background intellectual property used in providing the Services shall transfer to the Client upon creation, without additional compensation to the Supplier.

6. Termination
6.1 Either party may terminate this Agreement on 30 days' written notice.

7. Governing Law and Disputes
7.1 This Agreement is governed by the laws of England and Wales. The courts of England and Wales shall have exclusive jurisdiction.
"""

class RiskLevel(str, Enum):
    RED = "RED"
    AMBER = "AMBER"
    GREEN = "GREEN"

class Clause(BaseModel):
    number: str
    heading: str = ""
    text: str
    category: str = "Other"

class Risk(BaseModel):
    id: str
    clause_number: str
    category: str
    risk_level: RiskLevel
    original_text: str
    issue: str
    sa_law_citation: str
    suggested_redline: str

class RiskSummary(BaseModel):
    red: int
    amber: int
    green: int
    overall_score: str

class AnalysisResult(BaseModel):
    summary: RiskSummary
    risks: list[Risk]

class ContractResponse(BaseModel):
    contract_id: str
    filename: str
    text: str
    clauses: list[Clause]
    analysis: AnalysisResult

class AnalyzeRequest(BaseModel):
    clauses: list[Clause]

class ChatRequest(BaseModel):
    query: str = Field(min_length=1)
    contract_context: str = ""

class ChatResponse(BaseModel):
    answer: str
    citations: list[str] = []
    legal_sources: list[dict[str, str]] = []

class RAGChatRequest(BaseModel):
    query: str = Field(min_length=1)

class RAGChatResponse(BaseModel):
    answer: str
    cited_clause_numbers: list[str] = []
    sa_statute_citation: str = ""
    suggested_followups: list[str] = []
    legal_sources: list[dict[str, str]] = []

class RedlineStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    PENDING = "PENDING"

class RedlineRecord(BaseModel):
    id: str
    contract_id: str
    clause_number: str
    original_text: str
    redlined_text: str
    status: RedlineStatus

class AcceptRedlineRequest(BaseModel):
    contract_id: str
    clause_number: str

class CustomRedlineRequest(BaseModel):
    contract_id: str
    clause_number: str
    custom_text: str = Field(min_length=1)

class LegalSearchRequest(BaseModel):
    query: str = Field(min_length=2)
    top_k: int = Field(default=5, ge=1, le=10)

class ContractCreationContext(BaseModel):
    processes_personal_data: bool = False
    counterparty_type: str | None = None
    contract_value_zar: float = 0
    governing_jurisdiction: str | None = None

CATEGORY_KEYWORDS = {
    "Warranty": ["warrant", "delivery"],
    "Data Protection": ["personal information", "personal data", "process", "operator"],
    "Indemnity": ["indemn", "hold harmless"],
    "IP": ["intellectual property", "background", "transfer"],
    "Termination": ["terminate", "termination", "notice"],
    "Dispute Resolution": ["governing law", "jurisdiction", "arbitration", "courts"],
}


def categorize(text: str) -> str:
    lowered = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return category
    return "Other"


def split_clauses(text: str) -> list[Clause]:
    matches = list(re.finditer(r"(?m)^(\d+(?:\.\d+)*)\s+([^\n]+)", text))
    clauses: list[Clause] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.start():end].strip()
        lines = block.splitlines()
        heading = match.group(2).strip() if len(lines) == 1 else ""
        clauses.append(Clause(number=match.group(1), heading=heading, text=block, category=categorize(block)))
    return clauses or [Clause(number="", text=text, category=categorize(text))]


def analysis_rule_matches(rule: dict[str, Any], clause: Clause) -> bool:
    text = clause.text.lower()
    rule_id = rule["id"]
    if rule_id == "FLAG_CPA_WARRANTY_BREACH":
        durations = [int(value) for value in re.findall(r"\b(\d{1,3})\s*days?\b", text)]
        return clause.category == "Warranty" and (any(days < 180 for days in durations) or "exclude" in text and "statutory" in text)
    if rule_id == "FLAG_UNLIMITED_INDEMNITY":
        return clause.category == "Indemnity" and ("indemn" in text or "hold harmless" in text) and not any(term in text for term in ("cap", "capped", "limited liability", "limitation of liability"))
    if rule_id == "FLAG_FOREIGN_JURISDICTION":
        return clause.category == "Dispute Resolution" and any(term in text for term in ("england", "wales", "delaware", "singapore", "foreign court"))
    return False


def make_risk(clause: Clause, rule: dict[str, Any], index: int) -> Risk:
    return Risk(id=f"risk-{index}", clause_number=clause.number, category=rule["category"], risk_level=RiskLevel(rule["severity"]), original_text=clause.text, issue=rule["default_issue"], sa_law_citation=rule["act_reference"], suggested_redline=rule["suggested_redline"])


def analyze_clauses(clauses: list[Clause]) -> AnalysisResult:
    risks: list[Risk] = []
    for clause in clauses:
        for rule in RULES_MATRIX["contract_analysis_triggers"]:
            if analysis_rule_matches(rule, clause):
                risks.append(make_risk(clause, rule, len(risks) + 1))
    red = sum(r.risk_level == RiskLevel.RED for r in risks)
    amber = sum(r.risk_level == RiskLevel.AMBER for r in risks)
    overall = "Needs attention" if red else "Review amber items" if amber else "Low risk"
    return AnalysisResult(summary=RiskSummary(red=red, amber=amber, green=max(0, len(clauses) - len(risks)), overall_score=overall), risks=risks)


def extract_text(filename: str, payload: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        document = fitz.open(stream=payload, filetype="pdf")
        return "\n\n".join(page.get_text() for page in document).strip()
    if suffix == ".docx":
        from docx import Document
        with tempfile.NamedTemporaryFile(suffix=suffix) as temp:
            temp.write(payload)
            temp.flush()
            return "\n\n".join(paragraph.text for paragraph in Document(temp.name).paragraphs).strip()
    raise HTTPException(status_code=415, detail="Only PDF and DOCX files are supported")


def gemini_json(prompt: str) -> Any | None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not genai:
        return None
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_CHAT_MODEL", "gemini-3.1-flash-lite"), system_instruction="You are a South African contract analyst. Return only valid JSON.")
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        return json.loads(response.text)
    except Exception:
        return None


def laws_africa_retrieve(query: str, top_k: int = 5) -> list[dict[str, str]]:
    """Retrieve current South African legal context from the Laws.Africa sandbox."""
    token = os.getenv("LAWS_AFRICA_API_TOKEN")
    kb_code = os.getenv("LAWS_AFRICA_KB_CODE", "legislation-za")
    if not token or token == "your-laws-africa-sandbox-token":
        return []
    payload = json.dumps({
        "text": query,
        "top_k": top_k,
        "filters": {"principal": True, "repealed": False, "frbr_place": "za"},
    }).encode("utf-8")
    request = Request(
        f"https://api.laws.africa/ai/v1/knowledge-bases/{kb_code}/retrieve",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return []
    sources: list[dict[str, str]] = []
    for result in data.get("results", []):
        metadata = result.get("metadata", {})
        source_url = metadata.get("portion_public_url") or metadata.get("public_url") or ""
        sources.append({
            "title": metadata.get("title", "Laws.Africa source"),
            "url": source_url,
            "text": result.get("content", {}).get("text", ""),
        })
    return sources


def creation_rule_matches(rule: dict[str, Any], context: ContractCreationContext) -> bool:
    condition = rule["trigger_condition"]
    value = getattr(context, condition["field"])
    operator = condition["operator"]
    expected = condition["value"]
    if operator == "EQUALS":
        return value == expected
    if operator == "IN":
        return value in expected
    if operator == "GREATER_THAN":
        return value > expected
    return False

@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "gemini": "configured" if os.getenv("GEMINI_API_KEY") else "demo-mode",
        "laws_africa": "configured" if os.getenv("LAWS_AFRICA_API_TOKEN") else "demo-mode",
        "database": count_records(),
        "phase2": {"parser": "pdfplumber/python-docx", "segmenter": "regex+Gemini fallback", "matcher": "sqlite-vec", "analyzer": "Gemini JSON+local fallback"},
    }

@app.post("/api/v1/legal-search")
def legal_search(request: LegalSearchRequest) -> dict[str, list[dict[str, str]]]:
    return {"sources": laws_africa_retrieve(request.query, request.top_k)}

@app.post("/api/v1/evaluate-creation-rules")
def evaluate_creation_rules(context: ContractCreationContext) -> dict[str, list[dict[str, Any]]]:
    matches = [
        rule for rule in RULES_MATRIX["contract_creation_triggers"]
        if creation_rule_matches(rule, context)
    ]
    return {"matched_rules": matches}

@app.get("/api/v1/demo-contract", response_model=ContractResponse)
def demo_contract() -> ContractResponse:
    clauses = split_clauses(DEMO_CONTRACT)
    analysis = analyze_clauses(clauses)
    contract_id = save_contract("Master Services Agreement — demo", DEMO_CONTRACT, [clause.model_dump() for clause in clauses], analysis.model_dump())
    return ContractResponse(contract_id=contract_id, filename="Master Services Agreement — demo", text=DEMO_CONTRACT, clauses=clauses, analysis=analysis)

@app.post("/api/v1/upload-contract", response_model=ContractResponse)
async def upload_contract(file: UploadFile = File(...)) -> ContractResponse:
    payload = await file.read()
    try:
        text = extract_text_from_file(payload, file.filename or "contract.pdf")
    except ValueError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    segmented = segment_clauses(text)
    analysis_result = analyze_clauses_with_gemini(segmented)
    clauses = [Clause(number=item["clause_number"], heading=item.get("title", ""), text=item["text"], category=item.get("category", "Other")) for item in segmented]
    analysis = AnalysisResult(
        summary=RiskSummary(**analysis_result.summary),
        risks=[Risk(id=item.id, clause_number=item.clause_number, category=item.category, risk_level=RiskLevel(item.risk_level), original_text=item.original_text, issue=item.issue_found, sa_law_citation=item.sa_law_citation, suggested_redline=item.suggested_redline) for item in analysis_result.risks],
    )
    filename = file.filename or "uploaded contract"
    contract_id = save_contract(filename, text, [clause.model_dump() for clause in clauses], analysis.model_dump())
    return ContractResponse(contract_id=contract_id, filename=filename, text=text, clauses=clauses, analysis=analysis)

@app.post("/api/v1/analyze-risks", response_model=AnalysisResult)
def analyze_risks(request: AnalyzeRequest) -> AnalysisResult:
    return analyze_clauses(request.clauses)

@app.post("/api/v1/contracts/{contract_id}/chat", response_model=RAGChatResponse)
def contract_chat(contract_id: str, request: RAGChatRequest) -> RAGChatResponse:
    try:
        history = get_chat_history(contract_id)
        result = answer_contract_question(contract_id, request.query, history)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    save_chat_message(contract_id, "user", request.query)
    save_chat_message(contract_id, "assistant", result["answer"])
    return RAGChatResponse(**result)

@app.get("/api/v1/contracts/{contract_id}", response_model=ContractResponse)
def get_contract_state(contract_id: str) -> ContractResponse:
    contract = get_contract(contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail=f"Contract session not found: {contract_id}")
    redlines = list_redlines(contract_id)
    clauses = [Clause(**item) for item in apply_redlines_to_clauses(contract["clauses"], redlines)]
    analysis = AnalysisResult(**contract["analysis"])
    return ContractResponse(contract_id=contract_id, filename=contract["filename"], text=contract["text"], clauses=clauses, analysis=analysis)

@app.get("/api/v1/contracts/{contract_id}/redlines", response_model=list[RedlineRecord])
def get_contract_redlines(contract_id: str) -> list[RedlineRecord]:
    if not get_contract(contract_id):
        raise HTTPException(status_code=404, detail=f"Contract session not found: {contract_id}")
    return [RedlineRecord(**redline) for redline in list_redlines(contract_id)]

@app.post("/api/v1/redlines/accept", response_model=RedlineRecord)
def redlines_accept(request: AcceptRedlineRequest) -> RedlineRecord:
    try:
        return RedlineRecord(**accept_redline(request.contract_id, request.clause_number))
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

@app.post("/api/v1/redlines/custom", response_model=RedlineRecord)
def redlines_custom(request: CustomRedlineRequest) -> RedlineRecord:
    try:
        return RedlineRecord(**submit_custom_redline(request.contract_id, request.clause_number, request.custom_text))
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

@app.get("/api/v1/contracts/{contract_id}/export-pdf")
def export_contract_pdf_endpoint(contract_id: str) -> FileResponse:
    try:
        output_path = export_contract_pdf(contract_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return FileResponse(output_path, media_type="application/pdf", filename=f"{contract_id}-redlined.pdf")

@app.post("/api/v1/chat-qa", response_model=ChatResponse)
def chat_qa(request: ChatRequest) -> ChatResponse:
    legal_sources = laws_africa_retrieve(request.query)
    legal_context = "\n\n".join(
        f"Title: {source['title']}\nSource: {source['url']}\nText: {source['text']}"
        for source in legal_sources
    )
    prompt = f"Answer in plain language using only this contract context and authoritative legal context. Cite clause numbers exactly. Do not present legal information as legal advice. Query: {request.query}\nContract context:\n{request.contract_context}\nAuthoritative Laws.Africa context:\n{legal_context}"
    answer = gemini_json(prompt)
    if isinstance(answer, dict) and answer.get("answer"):
        return ChatResponse(answer=answer["answer"], citations=answer.get("citations", []), legal_sources=legal_sources)
    query = request.query.lower()
    if "popia" in query or "data" in query:
        return ChatResponse(answer="Clause 3.1 permits processing personal information but does not include explicit operator terms. Treat it as amber until a POPIA section 21 data processing addendum is signed.", citations=["3.1", "POPIA s21"], legal_sources=legal_sources)
    if "notice" in query or "termination" in query:
        return ChatResponse(answer="Clause 6.1 provides for 30 days' written notice by either party.", citations=["6.1"], legal_sources=legal_sources)
    return ChatResponse(answer="The clearest high-risk items are the 30-day warranty in clause 2.1, unlimited indemnity in clause 4.1, and background IP transfer in clause 5.1.", citations=["2.1", "4.1", "5.1"], legal_sources=legal_sources)
