from flask import Blueprint, request, jsonify, session
from models import db
from models.user import User

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

@auth_bp.post("/register")
def register():
    data = request.get_json(force=True)
    name, email, pw = data.get("name","").strip(), data.get("email","").strip().lower(), data.get("password","")
    if not name or not email or not pw:
        return jsonify({"error": "name, email, password required"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "email already registered"}), 409
    u = User(name=name, email=email)
    u.set_password(pw)
    db.session.add(u)
    db.session.commit()
    session["user_id"] = u.id
    return jsonify({"user": u.to_dict()}), 201

@auth_bp.post("/login")
def login():
    data = request.get_json(force=True)
    email, pw = data.get("email","").strip().lower(), data.get("password","")
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
