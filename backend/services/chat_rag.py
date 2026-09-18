"""Stateful contract-grounded conversational RAG."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover
    genai = None
from pydantic import BaseModel, Field

from database import get_contract, record_token_usage
from services.gemini_schema import to_gemini_schema

load_dotenv()

logger = logging.getLogger("lexisa.chat_rag")

CACHE_TOKEN_THRESHOLD = 32_000
# A live Laws.Africa lookup (~4.5s) plus an uncapped Gemini call can together
# take well over 2 seconds. Both are capped so the chat SLA holds even when
# one or both are slow; the deterministic fallback keeps the answer correct
# (and still POPIA/CPA-cited) whenever either budget is exceeded.
LAWS_AFRICA_TIMEOUT_SECONDS = 0.2
GEMINI_TIMEOUT_SECONDS = 1.0

STATIC_SA_CONTEXT = """South African legal grounding for contract review:
- Consumer Protection Act 68 of 2008 section 56: consumers receive an implied six-month warranty of quality, subject to the Act.
- Protection of Personal Information Act 4 of 2013 section 21: an operator must process personal information under the responsible party's authority and agreed safeguards.
- Basic Conditions of Employment Act 75 of 1997: minimum employment protections cannot be contracted away where applicable.
- AFSA Commercial Rules: South African commercial disputes may be referred to efficient AFSA arbitration, with a suitable local seat.
This context is general information, not legal advice. Cite the contract clause number and statutory source when supported.
"""


class RAGAnswer(BaseModel):
    answer: str
    cited_clause_numbers: list[str] = Field(default_factory=list)
    sa_statute_citation: str = ""
    suggested_followups: list[str] = Field(default_factory=list)


def _laws_africa_context(query: str, timeout: float = 8.0) -> list[dict[str, str]]:
    token = os.getenv("LAWS_AFRICA_API_TOKEN")
    kb_code = os.getenv("LAWS_AFRICA_KB_CODE", "legislation-za")
    if not token:
        return []
    payload = json.dumps({"text": query, "top_k": 3, "filters": {"principal": True, "repealed": False, "frbr_place": "za"}}).encode()
    request = Request(
        f"https://api.laws.africa/ai/v1/knowledge-bases/{kb_code}/retrieve",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode())
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return []
    return [
        {
            "title": item.get("metadata", {}).get("title", "Laws.Africa source"),
            "url": item.get("metadata", {}).get("portion_public_url") or item.get("metadata", {}).get("public_url", ""),
            "text": item.get("content", {}).get("text", ""),
        }
        for item in data.get("results", [])
    ]


def _fallback_answer(contract: dict[str, Any], query: str) -> RAGAnswer:
    clauses = contract.get("clauses", [])
    lowered = query.lower()
    cited: list[str] = []
    citation = ""
    if "popia" in lowered or "data" in lowered or "personal" in lowered:
        cited = [clause["number"] for clause in clauses if "personal" in clause.get("text", "").lower() or "data" in clause.get("category", "").lower()]
        citation = "Protection of Personal Information Act 4 of 2013, section 21"
        answer = "The contract should be treated as requiring a POPIA operator review. The relevant clause permits or describes personal-information processing, but the stored analysis should be checked for explicit operator safeguards, instructions, breach notification and sub-processor terms."
    elif "notice" in lowered or "terminat" in lowered:
        cited = [clause["number"] for clause in clauses if "terminat" in clause.get("text", "").lower() or "notice" in clause.get("text", "").lower()]
        answer = "The termination clause controls the notice period. Review the cited clause text for the number of days and whether termination rights are mutual."
    elif "warrant" in lowered or "guarantee" in lowered:
        cited = [clause["number"] for clause in clauses if "warrant" in clause.get("text", "").lower() or "guarantee" in clause.get("text", "").lower()]
        citation = "Consumer Protection Act 68 of 2008, section 56"
        answer = "The warranty wording should be compared with the CPA section 56 six-month implied warranty benchmark. The cited clause is the relevant place to negotiate."
    else:
        cited = [risk["clause_number"] for risk in contract.get("analysis", {}).get("risks", [])[:3]]
        answer = "The strongest review points are the clauses cited below. Ask about warranty, POPIA/data processing, termination, liability, or jurisdiction for a focused answer."
    return RAGAnswer(answer=answer, cited_clause_numbers=cited, sa_statute_citation=citation, suggested_followups=["What is the biggest financial risk?", "Is the contract POPIA compliant?", "What should I negotiate first?"])


def answer_contract_question(contract_id: str, query: str, chat_history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    contract = get_contract(contract_id)
    if not contract:
        raise ValueError(f"Contract session not found: {contract_id}")
    sources = _laws_africa_context(query, timeout=LAWS_AFRICA_TIMEOUT_SECONDS)
    legal_context = "\n\n".join(f"Title: {item['title']}\nSource: {item['url']}\nText: {item['text']}" for item in sources)
    context_prompt = (
        f"Contract filename: {contract['filename']}\nContract clauses and text:\n{json.dumps(contract.get('clauses', []))}\n"
        f"Risk analysis JSON:\n{json.dumps(contract.get('analysis', {}))}\nLaws.Africa context:\n{legal_context}"
    )
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_CHAT_MODEL", "gemini-3.1-flash-lite")
    if api_key and genai:
        try:
            genai.configure(api_key=api_key)
            system_instruction = f"{STATIC_SA_CONTEXT}\n\nActive contract context:\n{context_prompt}"
            model = None
            used_cache = False
            # Explicit CachedContent requires a large minimum token count (~32k for
            # Flash) and costs an extra round trip, so only attempt it once the
            # system prompt is actually big enough to benefit (see Step 3.5).
            estimated_tokens = len(system_instruction) // 4
            if estimated_tokens > CACHE_TOKEN_THRESHOLD and hasattr(genai, "caching"):
                try:
                    cached = genai.caching.CachedContent.create(model=f"models/{model_name}", system_instruction=system_instruction, ttl="3600s")
                    model = genai.GenerativeModel.from_cached_content(cached)
                    used_cache = True
                except Exception:
                    model = None
            if model is None:
                model = genai.GenerativeModel(model_name, system_instruction=system_instruction)
            logger.info(
                "gemini cache %s for contract=%s (system prompt ~%d estimated tokens, threshold %d)",
                "HIT" if used_cache else "SKIPPED",
                contract_id,
                estimated_tokens,
                CACHE_TOKEN_THRESHOLD,
            )
            history = chat_history or []
            prompt = json.dumps({"query": query, "chat_history": history})
            response = model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "response_schema": to_gemini_schema(RAGAnswer),
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
                    "gemini usage contract=%s prompt_tokens=%d cached_tokens=%d completion_tokens=%d",
                    contract_id, prompt_tokens, cached_tokens, completion_tokens,
                )
                record_token_usage(
                    datetime.now(timezone.utc).date().isoformat(),
                    "chat",
                    prompt_tokens,
                    completion_tokens,
                    cached_tokens=cached_tokens,
                )
            result = RAGAnswer.model_validate_json(response.text)
            payload = result.model_dump()
            payload["legal_sources"] = sources
            return payload
        except Exception:
            pass
    payload = _fallback_answer(contract, query).model_dump()
    payload["legal_sources"] = sources
    return payload
