"""Checkpoint 3.2: verify redline accept/custom persistence and GET readback."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from database import get_contract, init_db, save_contract
from services.redliner import accept_redline, apply_redlines_to_clauses, list_redlines, submit_custom_redline

CLAUSES = [
    {
        "number": "2.1",
        "heading": "Warranty",
        "text": "2.1 The Supplier warrants that the Services will materially conform to the Statement of Work for a period of 30 days from delivery.",
        "category": "Warranty",
    },
    {
        "number": "6.1",
        "heading": "Termination",
        "text": "6.1 Either party may terminate this Agreement on 30 days' written notice.",
        "category": "Termination",
    },
]

ANALYSIS = {
    "summary": {"red": 1, "amber": 0, "green": 1, "overall_score": "Needs attention"},
    "risks": [
        {
            "id": "risk-1",
            "clause_number": "2.1",
            "category": "Warranty",
            "risk_level": "RED",
            "original_text": CLAUSES[0]["text"],
            "issue": "The warranty is shorter than the six-month implied warranty period.",
            "sa_law_citation": "Consumer Protection Act 68 of 2008, section 56",
            "suggested_redline": (
                "The Supplier warrants that deliverables will be free from defects for a minimum period of six "
                "(6) months from delivery, in accordance with Section 56 of the Consumer Protection Act 68 of 2008."
            ),
        }
    ],
}

if __name__ == "__main__":
    init_db()
    contract_id = save_contract(
        "Checkpoint 3.2 sample contract",
        "\n\n".join(clause["text"] for clause in CLAUSES),
        CLAUSES,
        ANALYSIS,
    )

    # 1. Accept the suggested CPA warranty redline.
    accepted = accept_redline(contract_id, "2.1")
    print("accept_redline result:", accepted)
    assert accepted["status"] == "ACCEPTED"
    assert accepted["clause_number"] == "2.1"
    assert accepted["original_text"] == CLAUSES[0]["text"]
    assert "six (6) months" in accepted["redlined_text"]

    # 2. Fresh reads (new SQLite connections) simulate "subsequent GET calls".
    redlines_after = list_redlines(contract_id)
    assert len(redlines_after) == 1
    assert redlines_after[0]["status"] == "ACCEPTED"
    assert redlines_after[0]["redlined_text"] == accepted["redlined_text"]

    contract_after = get_contract(contract_id)
    overlaid_clauses = apply_redlines_to_clauses(contract_after["clauses"], redlines_after)
    clause_2_1 = next(clause for clause in overlaid_clauses if clause["number"] == "2.1")
    assert clause_2_1["text"] == accepted["redlined_text"], "Expected clause 2.1 text to reflect the accepted redline"
    clause_6_1 = next(clause for clause in overlaid_clauses if clause["number"] == "6.1")
    assert clause_6_1["text"] == CLAUSES[1]["text"], "Untouched clauses must remain unchanged"

    # 3. Re-accepting is idempotent and does not corrupt the stored original text.
    accepted_again = accept_redline(contract_id, "2.1")
    assert accepted_again["original_text"] == CLAUSES[0]["text"]
    assert len(list_redlines(contract_id)) == 1, "Expected an upsert, not a duplicate row"

    # 4. Custom attorney/SMME wording overrides the suggested redline for a different clause.
    custom = submit_custom_redline(contract_id, "6.1", "6.1 Either party may terminate this Agreement on 60 days' written notice.")
    print("submit_custom_redline result:", custom)
    assert custom["status"] == "ACCEPTED"
    assert "60 days" in custom["redlined_text"]

    redlines_final = list_redlines(contract_id)
    assert len(redlines_final) == 2
    contract_final = get_contract(contract_id)
    overlaid_final = apply_redlines_to_clauses(contract_final["clauses"], redlines_final)
    clause_6_1_final = next(clause for clause in overlaid_final if clause["number"] == "6.1")
    assert "60 days" in clause_6_1_final["text"]

    print("Checkpoint 3.2 passed")
