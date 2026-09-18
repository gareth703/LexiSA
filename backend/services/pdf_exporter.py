"""Redlined PDF export: executive summary, marked-up contract body, sign-off block."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from database import get_contract
from services.redliner import apply_redlines_to_clauses, list_redlines

EXPORTS_DIR = Path(__file__).parent.parent / "exports"

ACCEPTED_COLOR = colors.HexColor("#1a7a4c")
NEUTRAL_SIDEBAR = colors.HexColor("#d8ded8")
RED = colors.HexColor("#c0392b")
AMBER = colors.HexColor("#b8860b")
MUTED = colors.HexColor("#6b6d73")

CPA_CITATION = "Consumer Protection Act 68 of 2008 (CPA)"
POPIA_CITATION = "Protection of Personal Information Act 4 of 2013 (POPIA)"
BBBEE_CITATION = "Broad-Based Black Economic Empowerment Act 53 of 2003 (B-BBEE)"


def _styles() -> Any:
    stylesheet = getSampleStyleSheet()
    stylesheet.add(ParagraphStyle(name="ClauseNumber", fontName="Helvetica-Bold", fontSize=10, textColor=colors.HexColor("#33475b")))
    stylesheet.add(ParagraphStyle(name="ClauseBody", fontName="Helvetica", fontSize=10, leading=14))
    stylesheet.add(ParagraphStyle(name="RedlinedBody", fontName="Helvetica-Bold", fontSize=10, leading=14, textColor=ACCEPTED_COLOR))
    stylesheet.add(ParagraphStyle(name="RedlineBadge", fontName="Helvetica-Bold", fontSize=8, textColor=ACCEPTED_COLOR, spaceAfter=2))
    stylesheet.add(ParagraphStyle(name="SummaryHeading", fontName="Helvetica-Bold", fontSize=16, spaceAfter=10))
    stylesheet.add(ParagraphStyle(name="RiskResolved", fontName="Helvetica", fontSize=10, textColor=ACCEPTED_COLOR, leftIndent=10, spaceAfter=4))
    stylesheet.add(ParagraphStyle(name="RiskOutstandingRed", fontName="Helvetica-Bold", fontSize=10, textColor=RED, leftIndent=10, spaceAfter=4))
    stylesheet.add(ParagraphStyle(name="RiskOutstandingAmber", fontName="Helvetica", fontSize=10, textColor=AMBER, leftIndent=10, spaceAfter=4))
    return stylesheet


def _clause_flowable(clause: dict[str, Any], is_redlined: bool, styles: Any, content_width: float) -> Table:
    heading_text = f"Clause {clause['number']}" + (f" — {clause['heading']}" if clause.get("heading") else "")
    cell_content: list[Any] = [Paragraph(heading_text, styles["ClauseNumber"])]
    if is_redlined:
        cell_content.append(Paragraph("REDLINED — ACCEPTED", styles["RedlineBadge"]))
    cell_content.append(Spacer(1, 2))
    body_style = styles["RedlinedBody"] if is_redlined else styles["ClauseBody"]
    cell_content.append(Paragraph(clause["text"].replace("\n", "<br/>"), body_style))

    sidebar_width = 4 * mm
    sidebar_color = ACCEPTED_COLOR if is_redlined else NEUTRAL_SIDEBAR
    table = Table([["", cell_content]], colWidths=[sidebar_width, content_width - sidebar_width])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), sidebar_color),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (1, 0), (1, 0), 8),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _header_footer(canvas_obj: Any, doc_obj: Any) -> None:
    canvas_obj.saveState()
    canvas_obj.setFont("Helvetica-Bold", 8)
    canvas_obj.setFillColor(MUTED)
    canvas_obj.drawString(20 * mm, A4[1] - 12 * mm, "LEXISA CONTRACT INTELLIGENCE — REDLINED EXPORT")
    canvas_obj.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Page {doc_obj.page}")
    canvas_obj.restoreState()


def export_contract_pdf(contract_id: str) -> Path:
    contract = get_contract(contract_id)
    if not contract:
        raise ValueError(f"Contract session not found: {contract_id}")

    redlines = list_redlines(contract_id)
    accepted_clause_numbers = {redline["clause_number"] for redline in redlines if redline["status"] == "ACCEPTED"}
    overlaid_clauses = apply_redlines_to_clauses(contract["clauses"], redlines)

    risks = contract.get("analysis", {}).get("risks", [])
    resolved_risks = [risk for risk in risks if risk["clause_number"] in accepted_clause_numbers]
    outstanding_risks = [risk for risk in risks if risk["clause_number"] not in accepted_clause_numbers]
    summary = contract.get("analysis", {}).get("summary", {})

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = EXPORTS_DIR / f"{contract_id}.pdf"

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        topMargin=22 * mm,
        bottomMargin=20 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        title=f"LexiSA Redlined Export — {contract['filename']}",
    )
    styles = _styles()
    content_width = doc.width
    story: list[Any] = []

    # Executive SMME Compliance Summary (front page)
    story.append(Paragraph("Executive SMME Compliance Summary", styles["SummaryHeading"]))
    story.append(Paragraph(f"Contract: {contract['filename']}", styles["ClauseBody"]))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph(f"Resolved risks ({len(resolved_risks)})", styles["Heading2"]))
    if resolved_risks:
        for risk in resolved_risks:
            story.append(Paragraph(
                f"✓ Clause {risk['clause_number']} — {risk['category']}: {risk['issue']} ({risk['sa_law_citation']})",
                styles["RiskResolved"],
            ))
    else:
        story.append(Paragraph("No accepted redlines yet.", styles["ClauseBody"]))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph(f"Outstanding risks ({len(outstanding_risks)})", styles["Heading2"]))
    if outstanding_risks:
        for risk in outstanding_risks:
            style = styles["RiskOutstandingRed"] if risk["risk_level"] == "RED" else styles["RiskOutstandingAmber"]
            story.append(Paragraph(
                f"[{risk['risk_level']}] Clause {risk['clause_number']} — {risk['category']}: {risk['issue']} ({risk['sa_law_citation']})",
                style,
            ))
    else:
        story.append(Paragraph("No outstanding risks.", styles["ClauseBody"]))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph(
        f"Overall assessment: {summary.get('overall_score', 'n/a')} — "
        f"RED {summary.get('red', 0)}, AMBER {summary.get('amber', 0)}, GREEN {summary.get('green', 0)}.",
        styles["ClauseBody"],
    ))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        f"Compliance benchmarks referenced: {CPA_CITATION}; {POPIA_CITATION}; {BBBEE_CITATION}.",
        styles["ClauseBody"],
    ))
    story.append(PageBreak())

    # Redlined contract body
    story.append(Paragraph(contract["filename"], styles["SummaryHeading"]))
    story.append(HRFlowable(width="100%", color=NEUTRAL_SIDEBAR))
    story.append(Spacer(1, 4 * mm))
    for clause in overlaid_clauses:
        story.append(_clause_flowable(clause, clause["number"] in accepted_clause_numbers, styles, content_width))
        story.append(Spacer(1, 4 * mm))

    # Attorney sign-off block
    story.append(PageBreak())
    story.append(Paragraph("Attorney Sign-Off", styles["SummaryHeading"]))
    story.append(Paragraph(
        "This document reflects accepted redlines generated by LexiSA and is provided for review. It does not "
        "constitute legal advice until reviewed and countersigned by a practising South African attorney.",
        styles["ClauseBody"],
    ))
    story.append(Spacer(1, 14 * mm))
    sign_off_table = Table(
        [
            ["Attorney name:", "_" * 40],
            ["Practice number:", "_" * 40],
            ["Signature:", "_" * 40],
            ["Date:", "_" * 40],
        ],
        colWidths=[40 * mm, content_width - 40 * mm],
    )
    sign_off_table.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
    ]))
    story.append(sign_off_table)

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return output_path
