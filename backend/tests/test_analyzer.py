"""Checkpoint 2.4: verify structured risk output for a known contract."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from services.analyzer import analyze_clauses_with_gemini


if __name__ == "__main__":
    clauses = [
        {
            "clause_number": "2.1",
            "title": "Warranty",
            "category": "Warranty",
            "text": "2.1 Warranty: The Provider warrants the Services for 30 days.",
        },
        {
            "clause_number": "3.1",
            "title": "Data Processing",
            "category": "Data Privacy",
            "text": "3.1 The Provider processes personal information as an operator.",
        },
    ]
    result = analyze_clauses_with_gemini(clauses)
    print(result.model_dump_json(indent=2))
    assert isinstance(result.summary["red"], int)
    assert all(item.risk_level in {"RED", "AMBER", "GREEN"} for item in result.risks)
    print("Checkpoint 2.4 passed")