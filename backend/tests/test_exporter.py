"""Checkpoint 3.3: verify the redlined PDF export writes a well-formed document."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import fitz

from database import init_db, save_contract
from services.pdf_exporter import EXPORTS_DIR, export_contract_pdf
from services.redliner import accept_redline

CLAUSES = [
    {
        "number": "2.1",
        "heading": "Warranty",
        "text": "2.1 The Supplier warrants that the Services will materially conform to the Statement of Work for a period of 30 days from delivery.",
        "category": "Warranty",
    },
    {
        "number": "3.1",
        "heading": "Client Data",
        "text": "3.1 The Supplier may process personal information supplied by the Client in connection with the Services.",
        "category": "Data Protection",
    },
]

ANALYSIS = {
    "summary": {"red": 1, "amber": 1, "green": 0, "overall_score": "Needs attention"},
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
        },
        {
            "id": "risk-2",
            "clause_number": "3.1",
            "category": "Data Protection",
            "risk_level": "AMBER",
            "original_text": CLAUSES[1]["text"],
            "issue": "Personal information may be processed without documented operator terms.",
            "sa_law_citation": "POPIA 4 of 2013, section 21",
            "suggested_redline": "The parties will enter into an Operator data processing addendum.",
        },
    ],
}

if __name__ == "__main__":
    init_db()
    contract_id = save_contract(
        "Checkpoint 3.3 sample contract",
        "\n\n".join(clause["text"] for clause in CLAUSES),
        CLAUSES,
        ANALYSIS,
    )

    # Resolve the CPA warranty risk; leave the POPIA risk outstanding.
    accept_redline(contract_id, "2.1")

    output_path = export_contract_pdf(contract_id)
    print("PDF saved to:", output_path)

    assert output_path.exists(), "Expected the PDF to be written to disk"
    assert output_path.parent == EXPORTS_DIR, "Expected the PDF under backend/exports/"
    assert output_path.parent == Path(__file__).parents[1] / "exports"
    assert output_path.stat().st_size > 1000, "Expected a non-trivial PDF file"

    document = fitz.open(output_path)
    assert document.page_count >= 3, "Expected a summary page, contract body, and sign-off page"
    full_text = " ".join(" ".join(page.get_text().split()) for page in document)
    metadata_title = document.metadata.get("title", "")
    document.close()

    assert "LEXISA CONTRACT INTELLIGENCE" in full_text.upper(), "Expected the header on every page"
    assert "Executive SMME Compliance Summary" in full_text
    assert "Resolved risks (1)" in full_text
    assert "Outstanding risks (1)" in full_text
    assert "Consumer Protection Act" in full_text
    assert "Protection of Personal Information Act" in full_text
    assert "B-BBEE" in full_text or "Black Economic Empowerment" in full_text
    assert "REDLINED" in full_text.upper() and "ACCEPTED" in full_text.upper(), "Expected redline markup on the accepted clause"
    assert "six (6) months" in full_text, "Expected the accepted redline wording in the contract body"
    assert "Attorney Sign-Off" in full_text
    assert "Practice number" in full_text
    assert metadata_title, "Expected a PDF title"

    print("Checkpoint 3.3 passed")
