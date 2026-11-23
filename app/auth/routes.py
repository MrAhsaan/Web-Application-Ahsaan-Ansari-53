from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash
from app.database import get_db, now


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or len(username) > 100 or len(password) > 256:
            flash("Invalid username or password.", "error")
            return render_template("login.html")
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username=? AND is_active=1",
            (username,),
        ).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["user_role"] = user["role"]
            session["user_name"] = user["name"]
            session["csrf_token"] = __import__("secrets").token_urlsafe(32)
            db.execute("UPDATE users SET last_login=?, updated_at=? WHERE id=?", (now(), now(), user["id"]))
            db.commit()
            next_url = request.args.get("next") or url_for("dashboard.dashboard")
            if not next_url.startswith("/") or next_url.startswith("//"):
                next_url = url_for("dashboard.dashboard")
            return redirect(next_url)
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@auth_bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("bookings.main_home"))
