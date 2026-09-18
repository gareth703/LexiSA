"""Verify Laws.Africa retrieval for a South African rules-engine query."""
from __future__ import annotations

from main import laws_africa_retrieve


def query_sa_legislation(query: str) -> list[dict[str, str]]:
    return laws_africa_retrieve(query, top_k=5)


if __name__ == "__main__":
    results = query_sa_legislation("consumer implied warranty 6 months")
    print(f"Retrieved {len(results)} relevant SA Act sections.")
    for result in results:
        print(f"\n{result['title']}\n{result['url']}\n{result['text'][:500]}")
