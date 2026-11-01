"""Database-backed rate limiting for login, registration and validation.

Limits are sliding windows counted in the rate_limit_hits table, so they hold
across serverless instances. They are disabled in automated tests (TESTING)
unless RATELIMIT_ENABLED is set explicitly. Each limit can be overridden with
an environment variable, e.g. RATELIMIT_VALIDATE="30/60" (30 per 60 seconds).
"""
import logging
import os
import random
from datetime import datetime, timedelta
from functools import wraps

from flask import current_app, jsonify, request, session
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import SQLAlchemyError

from models import db
from models.rate_limit import RateLimitHit

logger = logging.getLogger("addressguard.ratelimit")

# name: (default limit, window seconds, keyed by user when logged in)
LIMITS = {
    "login": ("10/300", False),
    "register": ("5/3600", False),
    "validate": ("30/60", True),
    "validate_daily": ("500/86400", True),
    "bulk": ("5/3600", True),  # up to 50 addresses per upload
}


def _limit(name):
    raw, per_user = LIMITS[name]
    raw = os.getenv(f"RATELIMIT_{name.upper()}", raw)
    count, seconds = (int(x) for x in raw.split("/"))
    return count, seconds, per_user


def client_ip():
    # On Vercel the platform sets X-Forwarded-For to the real client address;
    # elsewhere the header is client-controlled, so the socket address is used.
    if os.getenv("VERCEL"):
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _enabled():
    explicit = os.getenv("RATELIMIT_ENABLED")
    if explicit is not None:
        return explicit.strip().lower() in {"1", "true", "yes", "on"}
    return not current_app.config.get("TESTING")


def _over_limit(names):
    """Record this request and return seconds to wait if any named limit is exceeded.

    All limits are checked with one grouped query and recorded in one commit:
    each database round trip costs about 0.2 s from India to Neon in the US.
    """
    now = datetime.utcnow()
    limits = {}
    for name in names:
        count, seconds, per_user = _limit(name)
        who = f"user:{session['user_id']}" if per_user and session.get("user_id") else f"ip:{client_ip()}"
        limits[f"{name}:{who}"] = (count, seconds)
    windows = or_(*(and_(RateLimitHit.key == key, RateLimitHit.created_at > now - timedelta(seconds=seconds))
                    for key, (_, seconds) in limits.items()))
    usage = {key: (n, oldest) for key, n, oldest in db.session.query(
        RateLimitHit.key, func.count(RateLimitHit.id), func.min(RateLimitHit.created_at))
        .filter(windows).group_by(RateLimitHit.key).all()}
    wait = 0
    for key, (count, seconds) in limits.items():
        used, oldest = usage.get(key, (0, None))
        if used >= count:
            wait = max(wait, int((oldest + timedelta(seconds=seconds) - now).total_seconds()) + 1, 1)
    if wait:
        return wait
    db.session.add_all(RateLimitHit(key=key, created_at=now) for key in limits)
    if random.random() < 0.01:  # occasional cleanup of expired hits
        RateLimitHit.query.filter(RateLimitHit.created_at < now - timedelta(days=2)).delete(synchronize_session=False)
    db.session.commit()
    return 0


def rate_limit(*names):
    """Reject the request with HTTP 429 when any of the named limits is exceeded."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if _enabled():
                try:
                    wait = _over_limit(names)
                except SQLAlchemyError:
                    # Never lock users out because the limiter itself failed.
                    db.session.rollback()
                    logger.exception("Rate limiter unavailable; request allowed")
                    wait = 0
                if wait:
                    response = jsonify({
                        "error": f"Too many requests. Please wait {wait} seconds and try again.",
                        "error_type": "RATE_LIMITED",
                    })
                    response.status_code = 429
                    response.headers["Retry-After"] = str(wait)
                    return response
            return view(*args, **kwargs)
        return wrapped
    return decorator
