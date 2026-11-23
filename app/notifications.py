"""Booking notification adapters with persistent attempt logs.

A provider accepting a message means it was submitted, not necessarily delivered.
Delivery receipts/webhooks are intentionally not claimed by this module.
"""
from email.message import EmailMessage
import re
import smtplib
import ssl
from datetime import datetime

from flask import current_app

from app.database import get_db, now

E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def _mask_recipient(channel, recipient):
    if not recipient:
        return None
    value = str(recipient).strip()
    if channel == "email" and "@" in value:
        local, domain = value.rsplit("@", 1)
        return f"{(local[:1] or '*')}***@{domain}"
    digits = re.sub(r"\D", "", value)
    return f"***{digits[-4:]}" if digits else "***"


def _message_text(booking, new_status):
    return (
        f"Hello {booking.get('customer_name') or 'Customer'},\n\n"
        f"Your AutoCare Garage booking {booking.get('booking_no') or booking.get('id')} has been updated.\n"
        f"Status: {new_status}\n"
        f"Service: {booking.get('service_name') or 'Service appointment'}\n"
        f"Vehicle: {booking.get('registration') or ''} {booking.get('brand') or ''} {booking.get('model') or ''}\n"
        f"Appointment: {booking.get('date')} at {booking.get('time')}\n"
        + (f"Fixed home-visit charge: INR {float(booking.get('home_visit_charge') or 0):.2f}\n"
           f"Pay securely here: {booking.get('payment_url')}\n"
           "Staff will be dispatched only after payment is verified. Repair costs are estimated separately after inspection.\n"
           if booking.get("payment_url") else "")
        + "\nIf you need help, please contact the garage.\nAutoCare Garage"
    )


def _send_email(recipient, subject, body, cfg):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["SMTP_FROM"]
    msg["To"] = recipient
    msg.set_content(body)
    timeout = int(cfg.get("SMTP_TIMEOUT", 15))
    if cfg.get("SMTP_USE_TLS", True):
        with smtplib.SMTP(cfg["SMTP_HOST"], int(cfg["SMTP_PORT"]), timeout=timeout) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            if cfg.get("SMTP_USERNAME"):
                server.login(cfg["SMTP_USERNAME"], cfg.get("SMTP_PASSWORD", ""))
            server.send_message(msg)
    else:
        with smtplib.SMTP(cfg["SMTP_HOST"], int(cfg["SMTP_PORT"]), timeout=timeout) as server:
            if cfg.get("SMTP_USERNAME"):
                server.login(cfg["SMTP_USERNAME"], cfg.get("SMTP_PASSWORD", ""))
            server.send_message(msg)
    return {"provider": "smtp", "message_id": msg.get("Message-ID"), "provider_status": "accepted_by_smtp"}


def _send_twilio(recipient, sender, body, cfg):
    # Imported only when a Twilio channel is enabled, so email-only/local installs
    # do not need to import or configure a live provider to start the app.
    from twilio.rest import Client

    client = Client(cfg["TWILIO_ACCOUNT_SID"], cfg["TWILIO_AUTH_TOKEN"])
    message = client.messages.create(body=body, from_=sender, to=recipient)
    return {
        "provider": "twilio",
        "message_id": getattr(message, "sid", None),
        "provider_status": getattr(message, "status", None) or "accepted_by_twilio",
    }


def _insert_log(db, booking, status, channel, recipient, outcome, provider=None,
                provider_message_id=None, provider_status=None, error_message=None):
    timestamp = now()
    cur = db.execute(
        """INSERT INTO notification_logs
           (booking_id,booking_no,event_status,channel,recipient_masked,status,provider,
            provider_message_id,provider_status,error_message,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (booking.get("id"), booking.get("booking_no"), status, channel,
         _mask_recipient(channel, recipient), outcome, provider, provider_message_id,
         provider_status, (str(error_message)[:500] if error_message else None), timestamp, timestamp),
    )
    db.commit()
    return cur.lastrowid


def notify_booking_status(booking, new_status, app=None):
    """Attempt email, SMS and opted-in WhatsApp notifications; log every channel.

    Provider errors are captured per channel. This function intentionally does not
    raise ordinary provider errors back into the booking workflow.
    """
    cfg = (app or current_app).config
    db = get_db()
    body = _message_text(booking, new_status)
    subject = f"AutoCare Garage booking {booking.get('booking_no') or booking.get('id')}: {new_status}"
    phone = (booking.get("phone") or "").strip()
    email = (booking.get("email") or "").strip()
    channels = [
        ("email", email),
        ("sms", phone),
        ("whatsapp", phone),
    ]
    results = []

    for channel, recipient in channels:
        provider = None
        sender = None
        skip_reason = None
        if not recipient:
            skip_reason = "Customer has no email address." if channel == "email" else "Customer has no phone number."
        elif channel == "email":
            provider = "smtp"
            configured = bool(cfg.get("NOTIFY_EMAIL") and cfg.get("SMTP_HOST") and cfg.get("SMTP_FROM"))
            if not configured:
                skip_reason = "Email notifications are not configured (SMTP host/from missing or disabled)."
        elif channel == "sms":
            provider = "twilio"
            sender = cfg.get("TWILIO_SMS_FROM", "").strip()
            if not (cfg.get("TWILIO_ACCOUNT_SID") and cfg.get("TWILIO_AUTH_TOKEN") and sender):
                skip_reason = "SMS is not configured (Twilio credentials/sender missing)."
            elif not E164_RE.fullmatch(recipient):
                skip_reason = "Phone number must use E.164 format, for example +919876543210."
                provider = None
        else:  # WhatsApp requires explicit customer consent per booking.
            provider = "twilio"
            sender = cfg.get("TWILIO_WHATSAPP_FROM", "").strip()
            if not booking.get("whatsapp_opt_in"):
                skip_reason = "Customer has not opted in to WhatsApp notifications."
            elif not (cfg.get("TWILIO_ACCOUNT_SID") and cfg.get("TWILIO_AUTH_TOKEN") and sender):
                skip_reason = "WhatsApp is not configured (Twilio credentials/sender missing)."
            elif not E164_RE.fullmatch(recipient):
                skip_reason = "Phone number must use E.164 format, for example +919876543210."
                provider = None
            else:
                recipient = f"whatsapp:{recipient}"
                if not sender.startswith("whatsapp:"):
                    sender = f"whatsapp:{sender}"

        if skip_reason:
            log_id = _insert_log(db, booking, new_status, channel, recipient, "skipped",
                                 provider=provider, error_message=skip_reason)
            results.append({"id": log_id, "channel": channel, "status": "skipped", "reason": skip_reason})
            continue

        # Write a recoverable attempt row before calling an external provider.
        log_id = _insert_log(db, booking, new_status, channel, recipient, "failed",
                             provider=provider, error_message="Attempt started; provider result not yet recorded.")
        try:
            if channel == "email":
                result = _send_email(recipient, subject, body, cfg)
            else:
                result = _send_twilio(recipient, sender, body, cfg)
            db.execute(
                """UPDATE notification_logs SET status='submitted',provider=?,provider_message_id=?,
                   provider_status=?,error_message=NULL,updated_at=? WHERE id=?""",
                (result.get("provider") or provider, result.get("message_id"),
                 result.get("provider_status"), now(), log_id),
            )
            db.commit()
            results.append({"id": log_id, "channel": channel, "status": "submitted"})
        except Exception as exc:  # provider/network failures must not undo booking updates
            db.execute(
                "UPDATE notification_logs SET status='failed',error_message=?,updated_at=? WHERE id=?",
                (f"{type(exc).__name__}: {exc}"[:500], now(), log_id),
            )
            db.commit()
            current_app.logger.warning("Booking notification failed: booking=%s channel=%s error=%s",
                                       booking.get("booking_no") or booking.get("id"), channel, type(exc).__name__)
            results.append({"id": log_id, "channel": channel, "status": "failed"})
    return results
