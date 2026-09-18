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
from pydantic import BaseModel, Field
from database import count_records, init_db, load_rules_matrix, save_contract

load_dotenv()
try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover
    genai = None

app = FastAPI(title="LexiSA Contract Intelligence API", version="0.1.0")
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
        model = genai.GenerativeModel("gemini-1.5-flash", system_instruction="You are a South African contract analyst. Return only valid JSON.")
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
    return ContractResponse(filename="Master Services Agreement — demo", text=DEMO_CONTRACT, clauses=clauses, analysis=analyze_clauses(clauses))

@app.post("/api/v1/upload-contract", response_model=ContractResponse)
async def upload_contract(file: UploadFile = File(...)) -> ContractResponse:
    payload = await file.read()
    text = extract_text(file.filename or "contract.pdf", payload)
    clauses = split_clauses(text)
    # Gemini is intentionally reserved for categorisation; local rules provide the guaranteed baseline.
    categorized = gemini_json(json.dumps({"task": "categorize clauses", "clauses": [c.model_dump() for c in clauses]}))
    if isinstance(categorized, list):
        for clause, result in zip(clauses, categorized):
            if isinstance(result, dict) and result.get("category"):
                clause.category = result["category"]
    analysis = analyze_clauses(clauses)
    save_contract(file.filename or "uploaded contract", analysis.model_dump())
    return ContractResponse(filename=file.filename or "uploaded contract", text=text, clauses=clauses, analysis=analysis)

@app.post("/api/v1/analyze-risks", response_model=AnalysisResult)
def analyze_risks(request: AnalyzeRequest) -> AnalysisResult:
    return analyze_clauses(request.clauses)

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
