import logging
import secrets
from datetime import datetime
from pathlib import Path
from flask import Flask, g, render_template, request, session
from .database import get_db, init_db


def create_app(test_config=None):
    # Templates and static assets live at the project root (../templates and ../static),
    # not under app/. Use absolute paths so startup is reliable from VS Code/PowerShell.
    project_root = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        template_folder=str(project_root / "templates"),
        static_folder=str(project_root / "static"),
    )
    app.config.from_object("config.Config")
    if test_config:
        app.config.update(test_config)
    if app.config.get("ENVIRONMENT") == "production":
        import os
        if not os.environ.get("AUTOCARE_SECRET", "").strip():
            raise RuntimeError("AUTOCARE_SECRET must be explicitly set in production.")
        app.config["SESSION_COOKIE_SECURE"] = True
        app.config["PROPAGATE_EXCEPTIONS"] = False

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app.logger.setLevel(logging.INFO)

    @app.before_request
    def csrf_protect():
        # Razorpay authenticates this server-to-server request with an HMAC signature.
        if request.endpoint == "bookings.razorpay_webhook":
            return
        if request.method == "POST":
            token = request.form.get("csrf_token", "")
            session_token = session.get("csrf_token")
            if not token or not session_token or not secrets.compare_digest(token, session_token):
                from flask import abort
                abort(400, description="Invalid or missing CSRF token.")

    @app.before_request
    def load_current_user():
        g.current_user = None
        user_id = session.get("user_id")
        if not user_id:
            return
        db = get_db()
        user = db.execute(
            "SELECT id,name,username,email,role,is_active FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
        if not user or not user["is_active"]:
            session.clear()
            return
        g.current_user = user
        session["user_role"] = user["role"]
        session["user_name"] = user["name"]

    @app.get("/health")
    def health_check():
        # A small readiness check that confirms both the app and database respond.
        get_db().execute("SELECT 1").fetchone()
        from flask import jsonify
        return jsonify(status="ok"), 200

    @app.context_processor
    def inject_globals():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return {
            "services": app.config["SERVICES"],
            "csrf_token": session["csrf_token"],
            "current_user": getattr(g, "current_user", None),
            "now_date": datetime.now().strftime("%Y-%m-%d"),
        }

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if app.config.get("ENVIRONMENT") == "production":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.teardown_appcontext
    def close_db(exception=None):
        db = g.pop("db", None)
        if db is not None:
            if exception:
                db.rollback()
            db.close()

    from .auth.routes import auth_bp
    from .dashboard.routes import dashboard_bp
    from .customers.routes import customers_bp
    from .bookings.routes import bookings_bp
    from .jobs.routes import jobs_bp
    from .invoices.routes import invoices_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(customers_bp)
    app.register_blueprint(bookings_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(invoices_bp)

    @app.errorhandler(400)
    def bad_request(error):
        return render_template("error.html", code=400, message=getattr(error, "description", "Bad request")), 400

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("error.html", code=403, message="You do not have permission to perform this action."), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("error.html", code=404, message="The requested page was not found."), 404

    @app.errorhandler(500)
    def server_error(error):
        app.logger.exception("Unhandled application error", exc_info=error)
        return render_template("error.html", code=500, message="Something went wrong. Please try again or contact the administrator."), 500

    with app.app_context():
        init_db()

    return app
