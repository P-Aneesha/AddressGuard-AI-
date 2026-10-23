from flask import Blueprint, request, jsonify, session
from models import db
from models.user import User
from utils.rate_limit import rate_limit

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _fields(*names):
    """Read text fields from a JSON object body; non-text values become ''."""
    data = request.get_json(silent=True)
    data = data if isinstance(data, dict) else {}
    return [data.get(n) if isinstance(data.get(n), str) else "" for n in names]

@auth_bp.post("/register")
@rate_limit("register")
def register():
    name, email, pw = _fields("name", "email", "password")
    name, email = name.strip(), email.strip().lower()
    if not name or not email or not pw:
        return jsonify({"error": "name, email, password required"}), 400
    if len(name) > 120 or len(email) > 160 or "@" not in email:
        return jsonify({"error": "Please enter a valid name and email address."}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "email already registered"}), 409
    u = User(name=name, email=email)
    u.set_password(pw)
    db.session.add(u)
    db.session.commit()
    session["user_id"] = u.id
    return jsonify({"user": u.to_dict()}), 201

@auth_bp.post("/login")
@rate_limit("login")
def login():
    email, pw = _fields("email", "password")
    email = email.strip().lower()
    u = User.query.filter_by(email=email).first()
    if not u or not u.check_password(pw):
        return jsonify({"error": "invalid credentials"}), 401
    session["user_id"] = u.id
    return jsonify({"user": u.to_dict()})

@auth_bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})

@auth_bp.get("/me")
def me():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"user": None})
    u = User.query.get(uid)
    return jsonify({"user": u.to_dict() if u else None})
