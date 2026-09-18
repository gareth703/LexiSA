"""Checkpoint 2.2: verify numbered clause segmentation."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from services.segmenter import segment_clauses

SAMPLE = """MASTER SERVICES AGREEMENT

1 Services
The Supplier provides implementation services.

2.1 Warranty
The Supplier warrants the Services for 30 days.

3.2 Data Processing
The Supplier processes personal information as an operator.

4.1 Governing Law
South African law applies and disputes use AFSA arbitration.
"""


if __name__ == "__main__":
    clauses = segment_clauses(SAMPLE, use_llm_fallback=False)
    print(clauses)
    assert [clause["clause_number"] for clause in clauses] == ["1", "2.1", "3.2", "4.1"]
    assert clauses[1]["category"] == "Warranty"
    assert clauses[2]["category"] == "Data Privacy"
    print("Checkpoint 2.2 passed")
