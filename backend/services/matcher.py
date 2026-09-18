"""Hybrid Gemini embedding and sqlite-vec rule matching."""
from __future__ import annotations

import json
import os
from typing import Any

import google.generativeai as genai
from dotenv import load_dotenv

from database import get_db_connection, init_db

load_dotenv()
EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-001")
DISTANCE_THRESHOLD = 0.65


def match_clause_to_rules(clause_text: str, top_k: int = 2) -> list[dict[str, Any]]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return []
    genai.configure(api_key=api_key)
    embedding_result = genai.embed_content(
        model=EMBEDDING_MODEL,
        content=clause_text,
        output_dimensionality=768,
    )
    embedding = embedding_result["embedding"]
    init_db()
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """SELECT v.rule_id, v.distance, r.category, r.act_reference,
                      r.severity, r.default_issue, r.suggested_redline, r.raw_json
               FROM vec_smme_rules v
               JOIN smme_rules r ON v.rule_id = r.id
               WHERE v.embedding MATCH ? AND k = ?
               ORDER BY v.distance ASC""",
            (json.dumps(embedding), top_k),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "rule_id": row[0],
            "distance": row[1],
            "category": row[2],
            "act_reference": row[3],
            "severity": row[4],
            "default_issue": row[5],
            "suggested_redline": row[6],
            "raw_json": row[7],
        }
        for row in rows
        if row[1] <= DISTANCE_THRESHOLD
    ]
