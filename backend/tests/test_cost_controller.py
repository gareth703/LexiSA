"""Checkpoint 3.5: verify daily token-quota enforcement and prompt-cache gating logs."""
from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parents[1]))

import services.chat_rag as chat_rag
from database import init_db, record_token_usage, save_contract
from middleware.cost_controller import DAILY_TOKEN_LIMIT, is_daily_quota_exceeded, is_metered_path

# usage_date is just a grouping key (TEXT column), not a real calendar date, so a
# fresh unique value per run keeps this test isolated from its own past runs.
SYNTHETIC_DATE = f"test-{uuid.uuid4().hex[:12]}"

ANALYSIS = {"summary": {"red": 0, "amber": 1, "green": 0, "overall_score": "Review amber items"}, "risks": []}


class _ListLogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record.getMessage())


def check_metered_paths() -> None:
    assert is_metered_path("/api/v1/contracts/abc-123/chat")
    assert is_metered_path("/api/v1/upload-contract")
    assert not is_metered_path("/api/v1/contracts/abc-123")
    assert not is_metered_path("/api/v1/health")
    print("Metered-path routing: OK")


def check_quota_tracking_and_enforcement() -> None:
    init_db()
    exceeded_before, used_before = is_daily_quota_exceeded(SYNTHETIC_DATE)
    assert not exceeded_before
    assert used_before == 0

    record_token_usage(SYNTHETIC_DATE, "chat", DAILY_TOKEN_LIMIT - 100, 0)
    exceeded, used = is_daily_quota_exceeded(SYNTHETIC_DATE)
    assert not exceeded and used == DAILY_TOKEN_LIMIT - 100

    record_token_usage(SYNTHETIC_DATE, "chat", 200, 0)
    exceeded, used = is_daily_quota_exceeded(SYNTHETIC_DATE)
    assert exceeded and used == DAILY_TOKEN_LIMIT + 100
    print(f"Quota tracking: {used}/{DAILY_TOKEN_LIMIT} tokens -> exceeded={exceeded}")


def check_cache_gating_logs() -> None:
    """A system prompt over CACHE_TOKEN_THRESHOLD must invoke CachedContent.create,
    and both cache-hit and per-turn token usage (incl. cached_content_token_count
    straight from Gemini's usage_metadata) must be logged."""
    init_db()
    huge_text = "The parties agree to comprehensive confidentiality obligations. " * 5000
    clauses = [{"number": "1.1", "heading": "Confidentiality", "text": huge_text, "category": "Other"}]
    contract_id = save_contract("Checkpoint 3.5 large contract", huge_text, clauses, ANALYSIS)

    fake_cached_model = MagicMock()
    fake_cached_model.generate_content.return_value = MagicMock(
        text='{"answer": "cached answer", "cited_clause_numbers": ["1.1"], "sa_statute_citation": "", "suggested_followups": []}',
        usage_metadata=MagicMock(prompt_token_count=5, cached_content_token_count=40000, candidates_token_count=10),
    )
    fake_caching = MagicMock()
    fake_caching.CachedContent.create.return_value = MagicMock()

    handler = _ListLogHandler()
    logger = logging.getLogger("lexisa.chat_rag")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    original_caching = getattr(chat_rag.genai, "caching", None)
    original_from_cached = chat_rag.genai.GenerativeModel.from_cached_content
    chat_rag.genai.caching = fake_caching
    chat_rag.genai.GenerativeModel.from_cached_content = MagicMock(return_value=fake_cached_model)
    try:
        result = chat_rag.answer_contract_question(contract_id, "Is this confidential?", [])
    finally:
        logger.removeHandler(handler)
        if original_caching is not None:
            chat_rag.genai.caching = original_caching
        else:
            delattr(chat_rag.genai, "caching")
        chat_rag.genai.GenerativeModel.from_cached_content = original_from_cached

    assert fake_caching.CachedContent.create.called, "Expected CachedContent.create for a system prompt over the threshold"
    assert result["answer"] == "cached answer", "Expected the (mocked) cached model's response to be used"

    cache_hit_logs = [message for message in handler.records if "cache HIT" in message]
    usage_logs = [message for message in handler.records if "cached_tokens=40000" in message]
    assert cache_hit_logs, f"Expected a 'cache HIT' log line, got: {handler.records}"
    assert usage_logs, f"Expected a log line reporting cached_content_token_count usage, got: {handler.records}"
    print("Cache gating log:", cache_hit_logs[0])
    print("Usage log:", usage_logs[0])


if __name__ == "__main__":
    check_metered_paths()
    check_quota_tracking_and_enforcement()
    check_cache_gating_logs()
    print("Checkpoint 3.5 passed")
