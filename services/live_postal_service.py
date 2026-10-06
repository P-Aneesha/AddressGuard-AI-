"""Live India postal lookup service.

Uses the public PincodeAPI.in V1 service as a live fallback/refresh layer.
The service is a community API that publishes Indian postal data sourced from
Department of Posts data. It is not itself an India Post government API.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
from typing import Any

try:
    from config import Config
except Exception:
    Config = None

logger = logging.getLogger("addressguard.live_postal")

BASE_URL = (getattr(Config, "LIVE_POSTAL_API_BASE_URL", None) or os.getenv("LIVE_POSTAL_API_BASE_URL", "https://api.pincodeapi.in/api/v1")).rstrip("/")
TIMEOUT = int(getattr(Config, "LIVE_POSTAL_API_TIMEOUT", None) or os.getenv("LIVE_POSTAL_API_TIMEOUT", "8"))
TTL = int(getattr(Config, "LIVE_POSTAL_CACHE_TTL_SECONDS", None) or os.getenv("LIVE_POSTAL_CACHE_TTL_SECONDS", "600"))
CACHE: dict[str, tuple[float, Any]] = {}


def enabled() -> bool:
    value = getattr(Config, "LIVE_POSTAL_API_ENABLED", None)
    if value is not None:
        return bool(value)
    return os.getenv("LIVE_POSTAL_API_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def _cached(key: str) -> Any | None:
    item = CACHE.get(key)
    if not item:
        return None
    ts, value = item
    if time.time() - ts > TTL:
        CACHE.pop(key, None)
        return None
    return value


def _put(key: str, value: Any) -> Any:
    CACHE[key] = (time.time(), value)
    return value


def _get_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "AddressGuard-AI/1.0 (+student-project)",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Unexpected live postal API response")
    return payload


def lookup_pincode(pincode: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not enabled():
        return [], {"enabled": False, "source": "disabled"}
    pin = "".join(ch for ch in str(pincode or "") if ch.isdigit())[:6]
    if len(pin) != 6:
        return [], {"enabled": True, "source": "invalid_input"}
    key = f"pin:{pin}"
    cached = _cached(key)
    if cached is not None:
        return cached, {"enabled": True, "source": "live_cache", "cached": True}
    try:
        payload = _get_json(f"{BASE_URL}/pincode/{urllib.parse.quote(pin)}")
        rows = payload.get("data", {}).get("post_offices", []) if payload.get("success") else []
        rows = rows if isinstance(rows, list) else []
        meta = payload.get("meta", {}) if isinstance(payload.get("meta"), dict) else {}
        return _put(key, rows), {
            "enabled": True,
            "source": "live",
            "dataset_version": meta.get("dataset_version", ""),
            "count": len(rows),
        }
    except Exception as exc:
        logger.warning("Live postal PIN lookup failed: %s", exc)
        return [], {"enabled": True, "source": "live_error", "error": type(exc).__name__}


def search(query: str, limit: int = 20) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not enabled():
        return [], {"enabled": False, "source": "disabled"}
    q = str(query or "").strip()
    if not q:
        return [], {"enabled": True, "source": "invalid_input"}
    limit = max(1, min(int(limit), 20))
    key = f"search:{q.lower()}:{limit}"
    cached = _cached(key)
    if cached is not None:
        return cached, {"enabled": True, "source": "live_cache", "cached": True}
    try:
        params = urllib.parse.urlencode({"q": q, "limit": limit, "offset": 0})
        payload = _get_json(f"{BASE_URL}/search?{params}")
        data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
        results = data.get("results", data.get("post_offices", []))
        results = results if isinstance(results, list) else []
        meta = payload.get("meta", {}) if isinstance(payload.get("meta"), dict) else {}
        return _put(key, results), {
            "enabled": True,
            "source": "live",
            "dataset_version": meta.get("dataset_version", ""),
            "count": len(results),
        }
    except Exception as exc:
        logger.warning("Live postal search failed for %r: %s", q, exc)
        return [], {"enabled": True, "source": "live_error", "error": type(exc).__name__}


def health() -> dict[str, Any]:
    if not enabled():
        return {"enabled": False, "status": "DISABLED"}
    try:
        payload = _get_json(f"{BASE_URL}/health")
        return {"enabled": True, "status": "UP", "response": payload}
    except Exception as exc:
        return {"enabled": True, "status": "DOWN", "error": type(exc).__name__}
