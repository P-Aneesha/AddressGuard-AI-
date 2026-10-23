import uuid
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON
from models import db
from services.decision_labels import normalize_decision

def json_type():
    try:
        return JSONB
    except Exception:
        return JSON

class Validation(db.Model):
    __tablename__ = "validations"
    id = db.Column(db.Integer, primary_key=True)
    validation_id = db.Column(db.String(64), unique=True, default=lambda: uuid.uuid4().hex[:12].upper())
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    raw_address = db.Column(db.Text, nullable=False)
    parsed_data = db.Column(db.JSON, nullable=False, default=dict)
    corrections = db.Column(db.JSON, nullable=False, default=list)
    confidence = db.Column(db.Integer, default=0)
    risk_level = db.Column(db.String(20), default="LOW")
    decision = db.Column(db.String(40), default="NEEDS CUSTOMER CONFIRMATION")
    pipeline = db.Column(db.JSON, nullable=False, default=list)
    explainability = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "validation_id": self.validation_id,
            "raw_address": self.raw_address,
            "parsed_data": self.parsed_data,
            "corrections": self.corrections,
            "confidence": self.confidence,
            "risk_level": self.risk_level,
            # Compatible mapping for any record that still holds a legacy label.
            "decision": normalize_decision(self.decision),
            "pipeline": self.pipeline,
            "explainability": self.explainability,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
