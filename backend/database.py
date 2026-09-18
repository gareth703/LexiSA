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
            text_content TEXT,
            clauses_json TEXT,
            analysis_json TEXT
        )
    """)
    existing_columns = {row[1] for row in cursor.execute("PRAGMA table_info(contracts)")}
    if "text_content" not in existing_columns:
        cursor.execute("ALTER TABLE contracts ADD COLUMN text_content TEXT")
    if "clauses_json" not in existing_columns:
        cursor.execute("ALTER TABLE contracts ADD COLUMN clauses_json TEXT")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contract_redlines (
            id TEXT PRIMARY KEY,
            contract_id TEXT,
            clause_number TEXT,
            original_text TEXT,
            redlined_text TEXT,
            status TEXT DEFAULT 'PENDING'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id TEXT,
            role TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS token_usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usage_date TEXT,
            endpoint TEXT,
            prompt_tokens INTEGER,
            cached_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def save_contract(filename: str, text: str, clauses: list[dict[str, Any]], analysis: dict[str, Any]) -> str:
    contract_id = str(uuid.uuid4())
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO contracts (id, filename, text_content, clauses_json, analysis_json) VALUES (?, ?, ?, ?, ?)",
        (contract_id, filename, text, json.dumps(clauses), json.dumps(analysis)),
    )
    conn.commit()
    conn.close()
    return contract_id


def get_contract(contract_id: str) -> dict[str, Any] | None:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT id, filename, text_content, clauses_json, analysis_json FROM contracts WHERE id = ?",
        (contract_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row["id"],
        "filename": row["filename"],
        "text": row["text_content"] or "",
        "clauses": json.loads(row["clauses_json"]) if row["clauses_json"] else [],
        "analysis": json.loads(row["analysis_json"]) if row["analysis_json"] else {},
    }


def save_chat_message(contract_id: str, role: str, content: str) -> None:
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO chat_messages (contract_id, role, content) VALUES (?, ?, ?)",
        (contract_id, role, content),
    )
    conn.commit()
    conn.close()


def get_chat_history(contract_id: str, limit: int = 20) -> list[dict[str, str]]:
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT role, content FROM chat_messages WHERE contract_id = ? ORDER BY id ASC LIMIT ?",
        (contract_id, limit),
    ).fetchall()
    conn.close()
    return [{"role": row["role"], "content": row["content"]} for row in rows]


def record_token_usage(usage_date: str, endpoint: str, prompt_tokens: int, completion_tokens: int, cached_tokens: int = 0) -> None:
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO token_usage_log (usage_date, endpoint, prompt_tokens, cached_tokens, completion_tokens, total_tokens) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (usage_date, endpoint, prompt_tokens, cached_tokens, completion_tokens, prompt_tokens + completion_tokens),
    )
    conn.commit()
    conn.close()


def get_daily_token_usage(usage_date: str) -> int:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT COALESCE(SUM(total_tokens), 0) FROM token_usage_log WHERE usage_date = ?",
        (usage_date,),
    ).fetchone()
    conn.close()
    return row[0] or 0


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
