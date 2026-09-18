"""SQLite and sqlite-vec persistence for LexiSA."""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

import sqlite_vec

DB_PATH = Path(__file__).with_name("lexisa.db")
RULES_PATH = Path(__file__).parent / "data" / "smme_rules_matrix.json"


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def load_rules_matrix() -> dict[str, list[dict[str, Any]]]:
    with RULES_PATH.open(encoding="utf-8") as rules_file:
        return json.load(rules_file)


def init_db() -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS smme_rules (
            id TEXT PRIMARY KEY,
            rule_type TEXT,
            category TEXT,
            act_reference TEXT,
            severity TEXT,
            default_issue TEXT,
            suggested_redline TEXT,
            raw_json TEXT
        )
    """)
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_smme_rules USING vec0(
            rule_id TEXT PRIMARY KEY,
            embedding float[768]
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
    conn.commit()
    conn.close()


def save_contract(filename: str, analysis: dict[str, Any]) -> str:
    contract_id = str(uuid.uuid4())
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO contracts (id, filename, analysis_json) VALUES (?, ?, ?)",
        (contract_id, filename, json.dumps(analysis)),
    )
    conn.commit()
    conn.close()
    return contract_id


def count_records() -> dict[str, int]:
    conn = get_db_connection()
    counts = {
        "smme_rules": conn.execute("SELECT COUNT(*) FROM smme_rules").fetchone()[0],
        "vector_rules": conn.execute("SELECT COUNT(*) FROM vec_smme_rules").fetchone()[0],
        "contracts": conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0],
    }
    conn.close()
    return counts


if __name__ == "__main__":
    init_db()
    print("SQLite database initialized with vector search support!")
