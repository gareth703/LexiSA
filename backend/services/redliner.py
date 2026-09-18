"""Contract redline / clause modification management.

Original clauses are stored immutably in ``contracts.clauses_json``. Accepted
redlines are tracked separately in ``contract_redlines`` and overlaid onto
clause text at read time, so the extracted document is never destructively
rewritten and repeat accepts stay idempotent.
"""
from __future__ import annotations

import uuid
from typing import Any

from database import get_contract, get_db_connection


def _find_clause(contract: dict[str, Any], clause_number: str) -> dict[str, Any] | None:
    return next((clause for clause in contract.get("clauses", []) if clause["number"] == clause_number), None)


def _find_suggested_redline(contract: dict[str, Any], clause_number: str) -> str | None:
    for risk in contract.get("analysis", {}).get("risks", []):
        if risk["clause_number"] == clause_number:
            return risk.get("suggested_redline")
    return None


def _upsert_redline(contract_id: str, clause_number: str, original_text: str, redlined_text: str, status: str) -> dict[str, Any]:
    conn = get_db_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM contract_redlines WHERE contract_id = ? AND clause_number = ?",
            (contract_id, clause_number),
        ).fetchone()
        redline_id = existing["id"] if existing else str(uuid.uuid4())
        if existing:
            conn.execute(
                "UPDATE contract_redlines SET redlined_text = ?, status = ? WHERE id = ?",
                (redlined_text, status, redline_id),
            )
        else:
            conn.execute(
                "INSERT INTO contract_redlines (id, contract_id, clause_number, original_text, redlined_text, status) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (redline_id, contract_id, clause_number, original_text, redlined_text, status),
            )
        conn.commit()
    finally:
        conn.close()
    return {
        "id": redline_id,
        "contract_id": contract_id,
        "clause_number": clause_number,
        "original_text": original_text,
        "redlined_text": redlined_text,
        "status": status,
    }


def accept_redline(contract_id: str, clause_number: str) -> dict[str, Any]:
    contract = get_contract(contract_id)
    if not contract:
        raise ValueError(f"Contract session not found: {contract_id}")
    clause = _find_clause(contract, clause_number)
    if not clause:
        raise ValueError(f"Clause not found: {clause_number}")
    suggested = _find_suggested_redline(contract, clause_number)
    if not suggested:
        raise ValueError(f"No suggested redline available for clause {clause_number}")
    return _upsert_redline(contract_id, clause_number, clause["text"], suggested, "ACCEPTED")


def submit_custom_redline(contract_id: str, clause_number: str, custom_text: str) -> dict[str, Any]:
    contract = get_contract(contract_id)
    if not contract:
        raise ValueError(f"Contract session not found: {contract_id}")
    clause = _find_clause(contract, clause_number)
    if not clause:
        raise ValueError(f"Clause not found: {clause_number}")
    return _upsert_redline(contract_id, clause_number, clause["text"], custom_text, "ACCEPTED")


def list_redlines(contract_id: str) -> list[dict[str, Any]]:
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT id, contract_id, clause_number, original_text, redlined_text, status "
            "FROM contract_redlines WHERE contract_id = ?",
            (contract_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def apply_redlines_to_clauses(clauses: list[dict[str, Any]], redlines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Overlay accepted redline text onto a copy of the pristine clause list."""
    accepted_by_clause = {redline["clause_number"]: redline["redlined_text"] for redline in redlines if redline["status"] == "ACCEPTED"}
    overlaid = []
    for clause in clauses:
        clause_copy = dict(clause)
        if clause_copy["number"] in accepted_by_clause:
            clause_copy["text"] = accepted_by_clause[clause_copy["number"]]
        overlaid.append(clause_copy)
    return overlaid
