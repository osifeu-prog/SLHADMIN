"""
SLH Guardian → slh-api client.

Mirrors local Guardian bot actions to the central Railway API at slh-api-production.up.railway.app,
so the `guardian_blacklist` and `guardian_reports` tables on Railway stay in sync with what the
Guardian bot sees locally.

Env:
    SLH_API_URL      — default https://slh-api-production.up.railway.app
    SLH_ADMIN_KEY    — required for admin endpoints (report, blacklist, alert)
    HTTP_TIMEOUT_S   — default 8

All calls are best-effort: on network/timeout failure we log and return None.
The Guardian bot must NEVER block on these calls.
"""
from __future__ import annotations

import os
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

API_URL = os.getenv("SLH_API_URL", "https://slh-api-production.up.railway.app").rstrip("/")
ADMIN_KEY = os.getenv("SLH_ADMIN_KEY", "")
TIMEOUT = float(os.getenv("HTTP_TIMEOUT_S", "8"))


def _headers(admin: bool = False) -> dict:
    h = {"Content-Type": "application/json", "User-Agent": "slh-guardian-bot/1.0"}
    if admin and ADMIN_KEY:
        h["X-Admin-Key"] = ADMIN_KEY
    return h


async def report_fraud(
    reporter_id: int,
    reported_user_id: int,
    reason: str,
    severity: str = "medium",
    evidence: Optional[str] = None,
    group_name: Optional[str] = None,
    reported_username: Optional[str] = None,
) -> Optional[dict]:
    """POST /api/guardian/report — files a fraud report on the central API."""
    url = f"{API_URL}/api/guardian/report"
    body = {
        "reporter_id": reporter_id,
        "reported_user_id": reported_user_id,
        "reason": reason,
        "severity": severity,
    }
    if evidence:
        body["evidence"] = evidence
    if group_name:
        body["group_name"] = group_name
    if reported_username:
        body["reported_username"] = reported_username
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.post(url, json=body, headers=_headers(admin=True))
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning("slh_api.report_fraud failed: %s", e)
        return None


async def check_user(user_id: int) -> Optional[dict]:
    """GET /api/guardian/check/{user_id} — returns flag status."""
    url = f"{API_URL}/api/guardian/check/{user_id}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get(url, headers=_headers())
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning("slh_api.check_user failed: %s", e)
        return None


async def fetch_blacklist(limit: int = 200, min_zuz: float = 0.0) -> Optional[list]:
    """GET /api/guardian/blacklist (admin) — pulls the canonical blacklist."""
    url = f"{API_URL}/api/guardian/blacklist"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get(url, params={"limit": limit, "min_zuz": min_zuz}, headers=_headers(admin=True))
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else data.get("users", [])
    except Exception as e:
        logger.warning("slh_api.fetch_blacklist failed: %s", e)
        return None


async def scan_message(text: str) -> Optional[dict]:
    """POST /api/guardian/scan-message — NLP risk score for a message body."""
    url = f"{API_URL}/api/guardian/scan-message"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.post(url, json={"text": text}, headers=_headers())
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning("slh_api.scan_message failed: %s", e)
        return None


async def get_stats() -> Optional[dict]:
    """GET /api/guardian/stats — aggregate fraud intel."""
    url = f"{API_URL}/api/guardian/stats"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get(url, headers=_headers())
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning("slh_api.get_stats failed: %s", e)
        return None


async def health_check() -> bool:
    """Quick ping /api/health."""
    try:
        async with httpx.AsyncClient(timeout=4.0) as c:
            r = await c.get(f"{API_URL}/api/health")
            return r.status_code == 200
    except Exception:
        return False
