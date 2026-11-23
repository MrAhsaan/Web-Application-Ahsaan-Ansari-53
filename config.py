import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.environ.get("AUTOCARE_SECRET") or secrets.token_hex(32)
    DATABASE = Path(os.environ.get("AUTOCARE_DB", BASE_DIR / "autocare.db"))
    ENVIRONMENT = os.environ.get("AUTOCARE_ENV", "development").lower()
    ADMIN_USER = os.environ.get("AUTOCARE_ADMIN_USER", "admin")
    ADMIN_PASSWORD = os.environ.get("AUTOCARE_ADMIN_PASSWORD") or secrets.token_urlsafe(12)
    ADMIN_PASSWORD_IS_GENERATED = not bool(os.environ.get("AUTOCARE_ADMIN_PASSWORD", "").strip())
    # Notifications are disabled unless the relevant provider credentials are configured.
    # Email uses SMTP; SMS and WhatsApp use Twilio.
    NOTIFY_EMAIL = os.environ.get("AUTOCARE_NOTIFY_EMAIL", "1").strip().lower() in {"1", "true", "yes", "on"}
    SMTP_HOST = os.environ.get("AUTOCARE_SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("AUTOCARE_SMTP_PORT", "587"))
    SMTP_USERNAME = os.environ.get("AUTOCARE_SMTP_USERNAME", "")
    SMTP_PASSWORD = os.environ.get("AUTOCARE_SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("AUTOCARE_SMTP_FROM", "")
    SMTP_USE_TLS = os.environ.get("AUTOCARE_SMTP_USE_TLS", "1").strip().lower() in {"1", "true", "yes", "on"}
    TWILIO_ACCOUNT_SID = os.environ.get("AUTOCARE_TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.environ.get("AUTOCARE_TWILIO_AUTH_TOKEN", "")
    TWILIO_SMS_FROM = os.environ.get("AUTOCARE_TWILIO_SMS_FROM", "")
    TWILIO_WHATSAPP_FROM = os.environ.get("AUTOCARE_TWILIO_WHATSAPP_FROM", "")
    NOTIFICATION_LOG_RETENTION_DAYS = int(os.environ.get("AUTOCARE_NOTIFICATION_LOG_RETENTION_DAYS", "180"))
    RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
    RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
    RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
    DEFAULT_HOME_VISIT_CHARGE = float(os.environ.get("AUTOCARE_HOME_VISIT_CHARGE", "299.00"))

    SERVICES = [
        "Mechanical Work", "Denting & Painting", "Washing & Detailing",
        "Electrical & Battery", "AC Service", "Tyres & Alignment",
        "Basic Service", "Premium Service", "Car Spa",
    ]

    # Security defaults. HTTPS should be enabled in production.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = env_bool("AUTOCARE_COOKIE_SECURE", ENVIRONMENT == "production")
    REMEMBER_COOKIE_HTTPONLY = True
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
    TRAP_HTTP_EXCEPTIONS = False
    PROPAGATE_EXCEPTIONS = False
