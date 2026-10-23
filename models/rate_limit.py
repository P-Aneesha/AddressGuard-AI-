from datetime import datetime

from models import db


class RateLimitHit(db.Model):
    """One request counted against a rate limit.

    Kept in the database because serverless instances (Vercel) share no
    memory, so an in-process counter would reset on every cold start.
    """
    __tablename__ = "rate_limit_hits"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(160), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (db.Index("ix_rate_limit_hits_key_created", "key", "created_at"),)
