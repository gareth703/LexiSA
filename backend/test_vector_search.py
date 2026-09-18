"""Run a semantic similarity check against embedded LexiSA rules."""
from __future__ import annotations

import json
import os
from typing import Any

import google.generativeai as genai
from dotenv import load_dotenv

from database import get_db_connection

EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-001")


def match_contract_clause(clause_text: str, top_k: int = 2) -> list[Any]:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required for vector search")
    genai.configure(api_key=api_key)
    embedding_result = genai.embed_content(model=EMBEDDING_MODEL, content=clause_text, output_dimensionality=768)
    clause_vector = embedding_result["embedding"]
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """SELECT v.rule_id, v.distance, r.category, r.act_reference,
                      r.severity, r.default_issue
               FROM vec_smme_rules v
               JOIN smme_rules r ON v.rule_id = r.id
               WHERE v.embedding MATCH ? AND k = ?
               ORDER BY v.distance ASC""",
            (json.dumps(clause_vector), top_k),
        ).fetchall()
        return rows
    finally:
        conn.close()


if __name__ == "__main__":
    sample_clause = "The warranty period for all services rendered under this agreement is strictly limited to 30 days from invoice date."
    print(f"Testing Clause: {sample_clause}\n")
    for match in match_contract_clause(sample_clause):
        print(f"Matched Rule ID: {match[0]} (Distance: {match[1]:.4f})")
        print(f"Category: {match[2]} | Severity: {match[4]}")
        print(f"Law Citation: {match[3]}")
        print(f"Issue: {match[5]}\n")
