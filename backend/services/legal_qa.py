"""General South African legal Q&A, not grounded to any specific contract.

Used by the "Query the South African Law" home-page path, where there is no
uploaded document to ground answers in. Shares the static SA legal primer,
live Laws.Africa lookup, and latency-bounded fallback pattern established in
``chat_rag.py`` for the contract-grounded RAG chat.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover
    genai = None
from pydantic import BaseModel, Field

from database import record_token_usage
from services.chat_rag import GEMINI_TIMEOUT_SECONDS, LAWS_AFRICA_TIMEOUT_SECONDS, STATIC_SA_CONTEXT, laws_africa_context
from services.gemini_schema import to_gemini_schema

load_dotenv()

logger = logging.getLogger("lexisa.legal_qa")


class LegalQAAnswer(BaseModel):
    answer: str
    sa_statute_citation: str = ""
    suggested_followups: list[str] = Field(default_factory=list)


def _fallback_answer(query: str) -> LegalQAAnswer:
    lowered = query.lower()
    if "popia" in lowered or "personal information" in lowered or "data" in lowered:
        answer = (
            "POPIA (Act 4 of 2013) requires a responsible party to process personal information lawfully and for "
            "a specific purpose, with appropriate security safeguards. An operator may only process personal "
            "information under the responsible party's authority and documented instructions."
        )
        citation = "Protection of Personal Information Act 4 of 2013, section 21"
    elif "warrant" in lowered or "consumer" in lowered or "cpa" in lowered:
        answer = (
            "The Consumer Protection Act 68 of 2008 implies a six-month warranty of quality for goods supplied "
            "to consumers, and this cannot be excluded or reduced by contract for qualifying consumers."
        )
        citation = "Consumer Protection Act 68 of 2008, section 56"
    elif "employ" in lowered or "leave" in lowered or "bcea" in lowered or "working hours" in lowered:
        answer = (
            "The Basic Conditions of Employment Act 75 of 1997 sets minimum standards, such as leave, working "
            "hours and notice periods, that cannot be contracted below for covered employees."
        )
        citation = "Basic Conditions of Employment Act 75 of 1997"
    elif "arbitrat" in lowered or "dispute" in lowered or "jurisdiction" in lowered:
        answer = (
            "South African commercial disputes can be referred to AFSA arbitration, which is generally faster "
            "and less costly than litigation, with a local seat such as Johannesburg, Cape Town or Durban."
        )
        citation = "AFSA Commercial Arbitration Rules"
    elif "bee" in lowered or "b-bbee" in lowered or "empowerment" in lowered:
        answer = (
            "The Broad-Based Black Economic Empowerment Act 53 of 2003 sets transformation requirements, and "
            "contracts above certain thresholds often require a supplier to maintain a B-BBEE certificate or "
            "sworn affidavit."
        )
        citation = "Broad-Based Black Economic Empowerment Act 53 of 2003"
    else:
        answer = (
            "Ask about a specific South African law topic such as POPIA (data protection), the CPA (consumer "
            "warranties), the BCEA (employment minimums), AFSA arbitration, or B-BBEE compliance for a focused answer."
        )
        citation = ""
    return LegalQAAnswer(
        answer=answer,
        sa_statute_citation=citation,
        suggested_followups=[
            "Is my business POPIA compliant?",
            "What warranty does the CPA require?",
            "How does AFSA arbitration work?",
        ],
    )


def answer_legal_question(query: str) -> dict[str, Any]:
    sources = laws_africa_context(query, timeout=LAWS_AFRICA_TIMEOUT_SECONDS)
    legal_context = "\n\n".join(f"Title: {item['title']}\nSource: {item['url']}\nText: {item['text']}" for item in sources)
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_CHAT_MODEL", "gemini-3.1-flash-lite")
    if api_key and genai:
        try:
            genai.configure(api_key=api_key)
            system_instruction = (
                f"{STATIC_SA_CONTEXT}\n\nYou are answering a general South African law question that is not tied "
                f"to any specific contract. Live legislative context:\n{legal_context}"
            )
            model = genai.GenerativeModel(model_name, system_instruction=system_instruction)
            response = model.generate_content(
                query,
                generation_config={
                    "response_mime_type": "application/json",
                    "response_schema": to_gemini_schema(LegalQAAnswer),
                    "temperature": 0,
                    "max_output_tokens": 512,
                },
                request_options={"timeout": GEMINI_TIMEOUT_SECONDS},
            )
            usage = getattr(response, "usage_metadata", None)
            if usage is not None:
                prompt_tokens = getattr(usage, "prompt_token_count", 0)
                cached_tokens = getattr(usage, "cached_content_token_count", 0)
                completion_tokens = getattr(usage, "candidates_token_count", 0)
                logger.info(
                    "gemini usage query=%r prompt_tokens=%d cached_tokens=%d completion_tokens=%d",
                    query, prompt_tokens, cached_tokens, completion_tokens,
                )
                record_token_usage(
                    datetime.now(timezone.utc).date().isoformat(),
                    "legal-qa",
                    prompt_tokens,
                    completion_tokens,
                    cached_tokens=cached_tokens,
                )
            result = LegalQAAnswer.model_validate_json(response.text)
            payload = result.model_dump()
            payload["legal_sources"] = sources
            return payload
        except Exception:
            pass
    payload = _fallback_answer(query).model_dump()
    payload["legal_sources"] = sources
    return payload
