"""Checkpoint 2.3: verify semantic matching against sqlite-vec."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from services.matcher import match_clause_to_rules


if __name__ == "__main__":
    matches = match_clause_to_rules("Warranty is 30 days")
    print(matches)
    assert matches, "Expected a semantic rule match"
    assert matches[0]["distance"] < 0.65
    assert "WARRANTY" in matches[0]["rule_id"] or "CPA" in matches[0]["rule_id"]
    print(f"Checkpoint 2.3 passed: {matches[0]['rule_id']} distance={matches[0]['distance']:.4f}")
