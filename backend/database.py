"""SQLite persistence for LexiSA contracts and South African risk rules."""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).with_name("lexisa.db")
RULES_PATH = Path(__file__).parent / "data" / "smme_rules_matrix.json"


def load_rules_matrix() -> dict[str, list[dict[str, Any]]]:
    with RULES_PATH.open(encoding="utf-8") as rules_file:
        return json.load(rules_file)


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(rules: dict[str, list[dict[str, Any]]] | None = None) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS risk_rules (
            id TEXT PRIMARY KEY,
            category TEXT,
            act_reference TEXT,
            trigger_condition TEXT,
            severity TEXT,
            default_issue TEXT,
            fallback_clause TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contracts (
            id TEXT PRIMARY KEY,
            filename TEXT,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            analysis_json TEXT
        )
    """)
    matrix = rules if rules is not None else load_rules_matrix()
    all_rules = matrix["contract_creation_triggers"] + matrix["contract_analysis_triggers"]
    seed_rows = [
        {
            "id": rule["id"],
            "category": rule.get("category", ""),
            "act_reference": rule.get("act_reference", ""),
            "trigger_condition": json.dumps(rule.get("trigger_condition"), sort_keys=True) if isinstance(rule.get("trigger_condition"), dict) else rule.get("trigger_condition", ""),
            "severity": rule.get("severity", rule.get("rule_type", "")),
            "default_issue": rule.get("default_issue", rule.get("prompt_instruction", "")),
            "fallback_clause": rule.get("suggested_redline", rule.get("prompt_instruction", "")),
        }
        for rule in all_rules
    ]
    cursor.executemany(
        """INSERT INTO risk_rules
        (id, category, act_reference, trigger_condition, severity, default_issue, fallback_clause)
        VALUES (:id, :category, :act_reference, :trigger_condition, :severity, :default_issue, :fallback_clause)
        ON CONFLICT(id) DO UPDATE SET
            category = excluded.category,
            act_reference = excluded.act_reference,
            trigger_condition = excluded.trigger_condition,
            severity = excluded.severity,
            default_issue = excluded.default_issue,
            fallback_clause = excluded.fallback_clause""",
        seed_rows,
    )
    placeholders = ",".join("?" for _ in seed_rows)
    cursor.execute(f"DELETE FROM risk_rules WHERE id NOT IN ({placeholders})", [row["id"] for row in seed_rows])
    conn.commit()
    conn.close()


def save_contract(filename: str, analysis: dict[str, Any]) -> str:
    contract_id = str(uuid.uuid4())
    conn = get_connection()
    conn.execute(
        "INSERT INTO contracts (id, filename, analysis_json) VALUES (?, ?, ?)",
        (contract_id, filename, json.dumps(analysis)),
    )
    conn.commit()
    conn.close()
    return contract_id


def count_records() -> dict[str, int]:
    conn = get_connection()
    counts = {
        "risk_rules": conn.execute("SELECT COUNT(*) FROM risk_rules").fetchone()[0],
        "contracts": conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0],
    }
    conn.close()
    return counts


if __name__ == "__main__":
    init_db()
    print("SQLite database initialized locally as lexisa.db!")
