"""Embed analysis rules into the local sqlite-vec index."""
from __future__ import annotations

import json
import os

import google.generativeai as genai
from dotenv import load_dotenv

from database import get_db_connection, init_db, load_rules_matrix

EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-001")


def hydrate_rules_vector_db() -> int:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required to embed the rules")
    genai.configure(api_key=api_key)
    init_db()
    rules = load_rules_matrix()["contract_analysis_triggers"]
    conn = get_db_connection()
    try:
        current_ids = [rule["id"] for rule in rules]
        placeholders = ",".join("?" for _ in current_ids)
        conn.execute(f"DELETE FROM smme_rules WHERE id NOT IN ({placeholders})", current_ids)
        conn.execute(f"DELETE FROM vec_smme_rules WHERE rule_id NOT IN ({placeholders})", current_ids)
        for rule in rules:
            text_to_embed = (
                f"Category: {rule['category']}. Trigger: {rule['trigger_condition']}. "
                f"Act: {rule['act_reference']}. Clause examples: warranty is 30 days; "
                f"unlimited indemnity; foreign governing law and courts."
            )
            embedding_result = genai.embed_content(model=EMBEDDING_MODEL, content=text_to_embed, output_dimensionality=768)
            embedding_vector = embedding_result["embedding"]
            if len(embedding_vector) != 768:
                raise ValueError(f"Expected 768 embedding values, got {len(embedding_vector)}")
            conn.execute(
                """INSERT OR REPLACE INTO smme_rules
                (id, rule_type, category, act_reference, severity, default_issue, suggested_redline, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rule["id"], rule["rule_type"], rule["category"], rule["act_reference"],
                    rule["severity"], rule["default_issue"], rule["suggested_redline"], json.dumps(rule),
                ),
            )
            conn.execute(
                "DELETE FROM vec_smme_rules WHERE rule_id = ?",
                (rule["id"],),
            )
            conn.execute(
                "INSERT INTO vec_smme_rules (rule_id, embedding) VALUES (?, ?)",
                (rule["id"], json.dumps(embedding_vector)),
            )
        conn.commit()
    finally:
        conn.close()
    return len(rules)


if __name__ == "__main__":
    print(f"Successfully ingested {hydrate_rules_vector_db()} rules into SQLite vector database!")
