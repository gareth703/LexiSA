"""Verify the general (no-contract) South African legal Q&A path."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from services.legal_qa import answer_legal_question

if __name__ == "__main__":
    started = time.perf_counter()
    result = answer_legal_question("Is my business POPIA compliant if I store customer emails?")
    elapsed = time.perf_counter() - started

    print(result)
    print(f"Elapsed: {elapsed:.3f}s")

    assert "21" in result["sa_statute_citation"], "Expected a reference to POPIA section 21"
    assert "POPIA" in result["sa_statute_citation"].upper() or "PROTECTION OF PERSONAL INFORMATION" in result["sa_statute_citation"].upper()
    assert result["suggested_followups"], "Expected follow-up suggestions"
    assert elapsed < 2.0, f"Expected a response within 2 seconds, took {elapsed:.3f}s"
    print("Legal Q&A checkpoint passed")
