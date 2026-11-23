from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]


def test_no_debug_server_default():
    text = (ROOT / "run.py").read_text()
    assert "AUTOCARE_DEBUG" in text
    assert "debug = False" not in text


def test_security_configuration_present():
    text = (ROOT / "config.py").read_text()
    for setting in ["SESSION_COOKIE_HTTPONLY", "SESSION_COOKIE_SAMESITE", "SESSION_COOKIE_SECURE", "MAX_CONTENT_LENGTH"]:
        assert setting in text


def test_csrf_and_security_headers_present():
    text = (ROOT / "app" / "__init__.py").read_text()
    assert "csrf_protect" in text
    assert "compare_digest" in text
    assert "X-Content-Type-Options" in text
    assert "X-Frame-Options" in text
    assert "Strict-Transport-Security" in text


def test_logout_is_post_only():
    text = (ROOT / "app" / "auth" / "routes.py").read_text()
    assert '@auth_bp.post("/logout")' in text


def test_database_foreign_keys_and_constraints():
    db_path = ROOT / "autocare.db"
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"users", "customers", "vehicles", "bookings", "job_cards", "job_items", "estimates", "invoices", "payments"}
        assert required.issubset(tables)
    finally:
        con.close()


def test_logout_form_posts_with_csrf_token():
    base = (ROOT / "templates" / "base.html").read_text()
    assert "method=\"POST\" action=\"{{ url_for('auth.logout') }}\"" in base
    assert 'name="csrf_token" value="{{ csrf_token }}"' in base


def test_readme_uses_actual_entrypoint():
    readme = (ROOT / "README.md").read_text()
    assert "python run.py" in readme
    assert "python app.py" not in readme


def test_fresh_database_has_no_transactional_records():
    con = sqlite3.connect(ROOT / "autocare.db")
    try:
        for table in ("customers", "vehicles", "bookings", "job_cards", "estimates", "estimate_items", "invoices", "payments"):
            assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    finally:
        con.close()


def test_flask_uses_project_root_templates_and_static_assets():
    text = (ROOT / "app" / "__init__.py").read_text()
    assert 'template_folder=str(project_root / "templates")' in text
    assert 'static_folder=str(project_root / "static")' in text
    assert (ROOT / "templates" / "home.html").is_file()
    assert (ROOT / "templates" / "base.html").is_file()
    assert (ROOT / "static" / "style.css").is_file()
    assert (ROOT / "static" / "app.js").is_file()


def test_all_referenced_local_template_files_exist():
    templates = ROOT / "templates"
    for name in ("home.html", "base.html", "error.html", "login.html", "dashboard.html"):
        assert (templates / name).is_file(), f"Missing template: {name}"


def test_production_deployment_files_exist():
    assert (ROOT / "wsgi.py").is_file()
    assert (ROOT / "requirements-production.txt").is_file()
    assert (ROOT / "DEPLOYMENT.md").is_file()
    assert "gunicorn" in (ROOT / "requirements-production.txt").read_text().lower()

def test_production_secret_and_admin_password_are_required():
    app_text = (ROOT / "app" / "__init__.py").read_text()
    db_text = (ROOT / "app" / "database.py").read_text()
    assert "AUTOCARE_SECRET must be explicitly set in production" in app_text
    assert "Set AUTOCARE_ADMIN_PASSWORD before first production startup" in db_text

def test_staff_management_routes_use_role_restrictions():
    customer_text = (ROOT / "app" / "customers" / "routes.py").read_text()
    jobs_text = (ROOT / "app" / "jobs" / "routes.py").read_text()
    invoice_text = (ROOT / "app" / "invoices" / "routes.py").read_text()
    assert "role_required" in customer_text
    assert 'role_required("admin", "manager", "technician")' in jobs_text
    assert 'role_required("admin", "manager", "receptionist")' in invoice_text

def test_public_booking_validates_contact_preference():
    booking_text = (ROOT / "app" / "bookings" / "routes.py").read_text()
    assert 'preferred_contact not in {"Phone", "Email", "WhatsApp"}' in booking_text

def test_health_endpoint_is_documented():
    app_text = (ROOT / "app" / "__init__.py").read_text()
    deploy_text = (ROOT / "DEPLOYMENT.md").read_text()
    assert '@app.get("/health")' in app_text
    assert "GET /health" in deploy_text


def test_home_faq_jinja_loop_is_closed_correctly():
    home = (ROOT / "templates" / "home.html").read_text()
    assert "('Can I pay online?'" in home
    assert "other payment methods.') ] %}" in home

def test_notification_schema_and_provider_configuration_are_present():
    schema = (ROOT / "app" / "database.py").read_text()
    config = (ROOT / "config.py").read_text()
    assert "CREATE TABLE IF NOT EXISTS notification_logs" in schema
    assert "whatsapp_opt_in" in schema
    for setting in ["SMTP_HOST", "TWILIO_ACCOUNT_SID", "TWILIO_SMS_FROM", "TWILIO_WHATSAPP_FROM"]:
        assert setting in config

def test_notification_documentation_explains_submitted_is_not_delivered():
    readme = (ROOT / "README.md").read_text().lower()
    assert "does **not** guarantee" in readme
    assert "notification logs" in readme
