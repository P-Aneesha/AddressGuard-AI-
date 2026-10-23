from flask import Blueprint, render_template, session, redirect, url_for

views_bp = Blueprint("views", __name__)

def _logged_in():
    return bool(session.get("user_id"))

@views_bp.get("/")
def index():
    # Public professional landing page. Authentication happens from the landing page.
    if _logged_in():
        return redirect(url_for("views.dashboard"))
    return render_template("index.html")

@views_bp.get("/login")
def login_page():
    if _logged_in():
        return redirect(url_for("views.dashboard"))
    return render_template("login.html")

@views_bp.get("/dashboard")
def dashboard():
    if not _logged_in():
        return redirect(url_for("views.login_page"))
    return render_template("dashboard.html")

@views_bp.get("/history")
def history_page():
    if not _logged_in():
        return redirect(url_for("views.login_page"))
    return render_template("history.html")
