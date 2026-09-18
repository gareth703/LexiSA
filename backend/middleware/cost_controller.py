"""Cost guardrails: daily Gemini token-spend tracking and quota enforcement.

Actual token counts are recorded by the Gemini-calling services themselves
(see ``services/chat_rag.py``, which reads ``response.usage_metadata`` after
every call). This middleware only enforces the daily cap: before a metered
request reaches its handler, it checks today's cumulative spend and rejects
with HTTP 429 if the quota is already used up.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from database import get_daily_token_usage

logger = logging.getLogger("lexisa.cost_controller")

DAILY_TOKEN_LIMIT = int(os.getenv("DAILY_TOKEN_LIMIT", "200000"))

# Only endpoints that actually invoke Gemini are metered against the cap.
METERED_PATH_SUFFIXES = ("/chat",)
METERED_EXACT_PATHS = ("/api/v1/upload-contract",)


def is_metered_path(path: str) -> bool:
    return path in METERED_EXACT_PATHS or path.endswith(METERED_PATH_SUFFIXES)


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def is_daily_quota_exceeded(usage_date: str | None = None) -> tuple[bool, int]:
    usage_date = usage_date or today()
    used = get_daily_token_usage(usage_date)
    return used >= DAILY_TOKEN_LIMIT, used


class CostControlMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        if is_metered_path(request.url.path):
            exceeded, used = is_daily_quota_exceeded()
            if exceeded:
                logger.warning("daily token quota exceeded: %d/%d used, rejecting %s", used, DAILY_TOKEN_LIMIT, request.url.path)
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": (
                            f"Daily Gemini token quota exceeded ({used}/{DAILY_TOKEN_LIMIT} tokens used today). "
                            "Please try again after midnight UTC."
                        )
                    },
                )
        return await call_next(request)
