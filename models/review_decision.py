from datetime import datetime

from models import db


class ReviewDecision(db.Model):
    """One human decision on a correction suggestion.

    action is "accepted" (suggestion used as given), "edited" (accepted after
    the reviewer changed the value) or "rejected". These rows are what the
    correction acceptance rate is measured from.
    """
    __tablename__ = "review_decisions"
    id = db.Column(db.Integer, primary_key=True)
    validation_id = db.Column(db.Integer, db.ForeignKey("validations.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    field = db.Column(db.String(40), nullable=False)
    original = db.Column(db.Text, nullable=False, default="")
    system_suggestion = db.Column(db.Text, nullable=False, default="")
    final_value = db.Column(db.Text, nullable=False, default="")
    action = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
