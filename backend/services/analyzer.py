"""Gemini-structured contract risk evaluation with deterministic fallback."""
from __future__ import annotations

import json
import os
from typing import Any

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover
    genai = None
from pydantic import BaseModel, Field

from services.matcher import match_clause_to_rules


class RiskItem(BaseModel):
    id: str
    clause_number: str
    category: str
    risk_level: str
    original_text: str
    issue_found: str
    sa_law_citation: str
    suggested_redline: str


class ContractAnalysisResult(BaseModel):
    summary: dict[str, Any]
    risks: list[RiskItem] = Field(default_factory=list)


def _candidate_is_relevant(rule_id: str, text: str) -> bool:
    lowered = text.lower()
    if rule_id == "FLAG_CPA_WARRANTY_BREACH":
        return "warrant" in lowered or "guarantee" in lowered
    if rule_id == "FLAG_UNLIMITED_INDEMNITY":
        return "indemn" in lowered or "hold harmless" in lowered
    if rule_id == "FLAG_FOREIGN_JURISDICTION":
        return any(term in lowered for term in ("governing law", "jurisdiction", "court", "arbitration"))
    return True


def _fallback_analysis(clauses: list[dict[str, str]], matches_by_clause: dict[str, list[dict[str, Any]]]) -> ContractAnalysisResult:
    risks: list[RiskItem] = []
    for clause in clauses:
        matches = matches_by_clause.get(clause["clause_number"], [])
        for match in matches:
            if match["severity"] not in {"RED", "AMBER", "GREEN"} or not _candidate_is_relevant(match["rule_id"], clause["text"]):
                continue
            risks.append(RiskItem(
                id=f"{match['rule_id']}-{clause['clause_number']}",
                clause_number=clause["clause_number"],
                category=match["category"],
                risk_level=match["severity"],
                original_text=clause["text"],
                issue_found=match["default_issue"],
                sa_law_citation=match["act_reference"],
                suggested_redline=match["suggested_redline"],
            ))
    red = sum(item.risk_level == "RED" for item in risks)
    amber = sum(item.risk_level == "AMBER" for item in risks)
    green = max(0, len(clauses) - len(risks))
    score = "Needs attention" if red else "Review amber items" if amber else "Low risk"
    return ContractAnalysisResult(summary={"red": red, "amber": amber, "green": green, "overall_score": score}, risks=risks)


def analyze_clauses_with_gemini(clauses: list[dict[str, str]]) -> ContractAnalysisResult:
    matches_by_clause: dict[str, list[dict[str, Any]]] = {}
    candidate_context: list[dict[str, Any]] = []
    for clause in clauses:
        try:
            matches = match_clause_to_rules(clause["text"])
        except Exception:
            matches = []
        matches_by_clause[clause["clause_number"]] = matches
        candidate_context.append({"clause": clause, "rule_matches": matches})

    api_key = os.getenv("GEMINI_API_KEY")
    if api_key and genai:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(
                os.getenv("GEMINI_CHAT_MODEL", "gemini-3.1-flash-lite"),
                system_instruction=(
                    "You are a South African contract risk analyst. Evaluate only the supplied clauses "
                    "and candidate rules. Return valid JSON matching the ContractAnalysisResult schema. "
                    "Use RED, AMBER, or GREEN and cite CPA, POPIA, BCEA, or another supplied SA reference."
                ),
            )
            response = model.generate_content(
                json.dumps(candidate_context),
                generation_config={
                    "response_mime_type": "application/json",
                    "response_schema": ContractAnalysisResult.model_json_schema(),
                },
            )
            return ContractAnalysisResult.model_validate_json(response.text)
        except Exception:
            pass
    return _fallback_analysis(clauses, matches_by_clause)
