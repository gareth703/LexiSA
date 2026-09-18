"""LexiSA API: lightweight contract intelligence for South African SMMEs."""
from __future__ import annotations

import json
import os
import re
import tempfile
from enum import Enum
from pathlib import Path
from typing import Any

import fitz
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()
try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover
    genai = None

app = FastAPI(title="LexiSA Contract Intelligence API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


def make_risk(clause: Clause, level: RiskLevel, issue: str, citation: str, redline: str, index: int) -> Risk:
    return Risk(id=f"risk-{index}", clause_number=clause.number, category=clause.category, risk_level=level, original_text=clause.text, issue=issue, sa_law_citation=citation, suggested_redline=redline)


def analyze_clauses(clauses: list[Clause]) -> AnalysisResult:
    risks: list[Risk] = []
    for clause in clauses:
        text = clause.text.lower()
        if clause.category == "Warranty" and re.search(r"\b(?:30|60|90)\s*days?\b", text):
            risks.append(make_risk(clause, RiskLevel.RED, "The warranty is shorter than the six-month implied warranty period.", "Consumer Protection Act 68 of 2008, section 56", "The Supplier warrants the Services for at least six months from delivery, subject to fair and reasonable exclusions permitted by the CPA.", len(risks) + 1))
        elif clause.category == "Data Protection" and "operator" not in text and "dpa" not in text:
            risks.append(make_risk(clause, RiskLevel.AMBER, "Personal information may be processed without the required operator terms, instructions and security commitments.", "POPIA 4 of 2013, section 21", "The parties will enter into an Operator data processing addendum covering documented instructions, confidentiality, security safeguards, sub-processors and breach notification.", len(risks) + 1))
        if clause.category == "Indemnity" and ("without limitation" in text or "any and all" in text):
            risks.append(make_risk(clause, RiskLevel.RED, "This creates an unlimited indemnity for the Supplier and does not allocate liability proportionately.", "Common-law proportionality; Constitution section 34 access to justice", "The Supplier's aggregate liability will be capped at fees paid in the preceding 12 months, with uncapped liability limited to fraud, wilful misconduct and confidentiality breaches.", len(risks) + 1))
        if clause.category == "IP" and "background" in text and "without additional compensation" in text:
            risks.append(make_risk(clause, RiskLevel.RED, "Background IP transfers without compensation, potentially giving away pre-existing SMME assets.", "Copyright Act 98 of 1978; contractual IP principles", "Each party retains its background IP. The Supplier grants the Client a non-exclusive licence to use Supplier background IP only as needed to receive the Services.", len(risks) + 1))
        if clause.category == "Dispute Resolution" and ("england" in text or "wales" in text or "overseas" in text):
            risks.append(make_risk(clause, RiskLevel.AMBER, "Overseas courts increase cost and enforcement friction for a South African SMME.", "International Arbitration Act 15 of 2017; AFSA Rules", "South African law applies and disputes will be referred to mediation, then AFSA arbitration seated in Johannesburg, in English.", len(risks) + 1))
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
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash", system_instruction="You are a South African contract analyst. Return only valid JSON.")
    response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
    try:
        return json.loads(response.text)
    except (json.JSONDecodeError, AttributeError):
        return None

@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "gemini": "configured" if os.getenv("GEMINI_API_KEY") else "demo-mode"}

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
    return ContractResponse(filename=file.filename or "uploaded contract", text=text, clauses=clauses, analysis=analyze_clauses(clauses))

@app.post("/api/v1/analyze-risks", response_model=AnalysisResult)
def analyze_risks(request: AnalyzeRequest) -> AnalysisResult:
    return analyze_clauses(request.clauses)

@app.post("/api/v1/chat-qa", response_model=ChatResponse)
def chat_qa(request: ChatRequest) -> ChatResponse:
    prompt = f"Answer in plain language using only this contract context. Cite clause numbers exactly. Query: {request.query}\nContext:\n{request.contract_context}"
    answer = gemini_json(prompt)
    if isinstance(answer, dict) and answer.get("answer"):
        return ChatResponse(answer=answer["answer"], citations=answer.get("citations", []))
    query = request.query.lower()
    if "popia" in query or "data" in query:
        return ChatResponse(answer="Clause 3.1 permits processing personal information but does not include explicit operator terms. Treat it as amber until a POPIA section 21 data processing addendum is signed.", citations=["3.1", "POPIA s21"])
    if "notice" in query or "termination" in query:
        return ChatResponse(answer="Clause 6.1 provides for 30 days' written notice by either party.", citations=["6.1"])
    return ChatResponse(answer="The clearest high-risk items are the 30-day warranty in clause 2.1, unlimited indemnity in clause 4.1, and background IP transfer in clause 5.1.", citations=["2.1", "4.1", "5.1"])
