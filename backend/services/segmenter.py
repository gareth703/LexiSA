"""Clause segmentation for numbered and poorly formatted contracts."""
from __future__ import annotations

import json
import os
import re
from typing import Any

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover
    genai = None

NUMBERED_CLAUSE = re.compile(r"(?m)^(?P<number>\d+(?:\.\d+)*|Clause\s+\d+|Section\s+\d+)\s*(?:[-.:)]\s*)?(?P<title>[^\n]*)")


def category_for(text: str) -> str:
    lowered = text.lower()
    categories = {
        "Warranty": ("warrant", "guarantee"),
        "Liability": ("liabil", "indemn", "damages"),
        "Data Privacy": ("personal data", "personal information", "popia", "operator"),
        "Jurisdiction": ("governing law", "jurisdiction", "court", "arbitration"),
        "Termination": ("terminate", "termination", "notice period"),
    }
    for category, terms in categories.items():
        if any(term in lowered for term in terms):
            return category
    return "Other"


def regex_segment(text: str) -> list[dict[str, str]]:
    matches = list(NUMBERED_CLAUSE.finditer(text))
    clauses: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.start():end].strip()
        title = match.group("title").strip()
        clauses.append({
            "clause_number": match.group("number").strip(),
            "title": title,
            "text": block,
            "category": category_for(block),
        })
    return clauses


def gemini_segment(text: str) -> list[dict[str, str]]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not genai:
        return []
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            "gemini-1.5-flash",
            system_instruction=(
                "Segment the contract into functional clauses. Return only a JSON array "
                "with clause_number, title, text, and category fields."
            ),
        )
        response = model.generate_content(
            text,
            generation_config={"response_mime_type": "application/json"},
        )
        result = json.loads(response.text)
        return result if isinstance(result, list) else []
    except Exception:
        return []


def segment_clauses(text: str, use_llm_fallback: bool = True) -> list[dict[str, str]]:
    clauses = regex_segment(text)
    if len(clauses) >= 3 or not use_llm_fallback:
        return clauses
    return gemini_segment(text) or clauses
