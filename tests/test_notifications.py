from pathlib import Path

import pytest

from app import create_app
from app.database import get_db, now

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key-not-for-production",
        "DATABASE": tmp_path / "test-autocare.db",
        "ENVIRONMENT": "testing",
        "ADMIN_USER": "testadmin",
        "ADMIN_PASSWORD": "test-password-only",
        "ADMIN_PASSWORD_IS_GENERATED": False,
        "NOTIFY_EMAIL": False,
        "SMTP_HOST": "",
        "SMTP_FROM": "",
        "TWILIO_ACCOUNT_SID": "",
        "TWILIO_AUTH_TOKEN": "",
        "TWILIO_SMS_FROM": "",
        "TWILIO_WHATSAPP_FROM": "",
        "RAZORPAY_KEY_ID": "rzp_test_key",
        "RAZORPAY_KEY_SECRET": "test-key-secret",
        "RAZORPAY_WEBHOOK_SECRET": "test-webhook-secret",
        "DEFAULT_HOME_VISIT_CHARGE": 299.0,
    })
    with app.app_context():
        db = get_db()
        service_id = db.execute("SELECT id FROM services LIMIT 1").fetchone()[0]
        stamp = now()
        customer_id = db.execute(
            "INSERT INTO customers(name,phone,email,created_at,updated_at) VALUES(?,?,?,?,?)",
            ("Test Customer", "+919876543210", "customer@example.com", stamp, stamp),
        ).lastrowid
        vehicle_id = db.execute(
            "INSERT INTO vehicles(customer_id,registration,brand,model,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (customer_id, "TEST123", "TestBrand", "TestModel", stamp, stamp),
        ).lastrowid
        booking_id = db.execute(
            """INSERT INTO bookings(booking_no,customer_id,vehicle_id,service_id,date,time,status,
               whatsapp_opt_in,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            ("ACTEST001", customer_id, vehicle_id, service_id, "2099-01-01", "10:00 AM", "Pending", 1, stamp, stamp),
        ).lastrowid
        db.commit()
        app.config["TEST_BOOKING_ID"] = booking_id
        app.config["TEST_ADMIN_ID"] = db.execute("SELECT id FROM users WHERE username='testadmin'").fetchone()[0]
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def _login_and_csrf(client, app):
    with client.session_transaction() as session:
        session["user_id"] = app.config["TEST_ADMIN_ID"]
        session["csrf_token"] = "test-csrf"
    return {"csrf_token": "test-csrf"}


def test_status_change_commits_then_calls_notifications(client, app, monkeypatch):
    calls = []
    import app.bookings.routes as routes
    monkeypatch.setattr(routes, "notify_booking_status", lambda booking, status, app=None: calls.append((booking["booking_no"], status)))
    data = _login_and_csrf(client, app)
    response = client.post(f"/admin/bookings/{app.config['TEST_BOOKING_ID']}/status", data={**data, "status": "Confirmed"})
    assert response.status_code == 302
    assert calls == [("ACTEST001", "Confirmed")]
    with app.app_context():
        assert get_db().execute("SELECT status FROM bookings WHERE id=?", (app.config["TEST_BOOKING_ID"],)).fetchone()[0] == "Confirmed"


def test_unchanged_status_does_not_send_duplicate_notification(client, app, monkeypatch):
    calls = []
    import app.bookings.routes as routes
    monkeypatch.setattr(routes, "notify_booking_status", lambda *args, **kwargs: calls.append(args))
    data = _login_and_csrf(client, app)
    response = client.post(f"/admin/bookings/{app.config['TEST_BOOKING_ID']}/status", data={**data, "status": "Pending"})
    assert response.status_code == 302
    assert calls == []


def test_notification_service_logs_provider_acceptance_and_whatsapp_opt_in(app, monkeypatch):
    import app.notifications as notifications
    monkeypatch.setattr(notifications, "_send_email", lambda *args: {"provider": "smtp", "message_id": "mail-test-id", "provider_status": "accepted_by_smtp"})
    monkeypatch.setattr(notifications, "_send_twilio", lambda *args: {"provider": "twilio", "message_id": "SM-test-id", "provider_status": "queued"})
    app.config.update({
        "NOTIFY_EMAIL": True, "SMTP_HOST": "smtp.example.com", "SMTP_FROM": "garage@example.com",
        "TWILIO_ACCOUNT_SID": "AC-test", "TWILIO_AUTH_TOKEN": "test-token",
        "TWILIO_SMS_FROM": "+14155550100", "TWILIO_WHATSAPP_FROM": "whatsapp:+14155550101",
    })
    booking = {"id": 1, "booking_no": "ACTEST001", "customer_name": "Test Customer", "email": "customer@example.com",
               "phone": "+919876543210", "date": "2099-01-01", "time": "10:00 AM", "service_name": "Basic Service",
               "whatsapp_opt_in": 1}
    with app.app_context():
        results = notifications.notify_booking_status(booking, "Confirmed", app=app)
        assert [r["status"] for r in results] == ["submitted", "submitted", "submitted"]
        rows = get_db().execute("SELECT channel,status,provider_message_id FROM notification_logs ORDER BY id").fetchall()
        assert [(r["channel"], r["status"]) for r in rows] == [("email", "submitted"), ("sms", "submitted"), ("whatsapp", "submitted")]
        assert rows[1]["provider_message_id"] == "SM-test-id"


def test_whatsapp_is_skipped_without_customer_consent(app, monkeypatch):
    import app.notifications as notifications
    monkeypatch.setattr(notifications, "_send_email", lambda *args: {"provider": "smtp", "message_id": None, "provider_status": "accepted_by_smtp"})
    app.config.update({"NOTIFY_EMAIL": False, "TWILIO_ACCOUNT_SID": "AC-test", "TWILIO_AUTH_TOKEN": "token", "TWILIO_SMS_FROM": "", "TWILIO_WHATSAPP_FROM": "whatsapp:+14155550101"})
    booking = {"id": 1, "booking_no": "ACTEST002", "customer_name": "Test Customer", "email": None,
               "phone": "+919876543210", "date": "2099-01-01", "time": "10:00 AM", "service_name": "Basic Service",
               "whatsapp_opt_in": 0}
    with app.app_context():
        results = notifications.notify_booking_status(booking, "Cancelled", app=app)
        assert results[2]["status"] == "skipped"
        row = get_db().execute("SELECT status,error_message FROM notification_logs WHERE channel='whatsapp'").fetchone()
        assert row["status"] == "skipped"
        assert "not opted in" in row["error_message"]


def test_provider_failure_is_logged_and_does_not_raise(app, monkeypatch):
    import app.notifications as notifications
    def fail(*args):
        raise OSError("SMTP unavailable")
    monkeypatch.setattr(notifications, "_send_email", fail)
    app.config.update({"NOTIFY_EMAIL": True, "SMTP_HOST": "smtp.example.com", "SMTP_FROM": "garage@example.com"})
    booking = {"id": 1, "booking_no": "ACTEST003", "customer_name": "Test Customer", "email": "customer@example.com",
               "phone": None, "date": "2099-01-01", "time": "10:00 AM", "service_name": "Basic Service", "whatsapp_opt_in": 0}
    with app.app_context():
        results = notifications.notify_booking_status(booking, "Confirmed", app=app)
        assert results[0]["status"] == "failed"
        row = get_db().execute("SELECT status,error_message FROM notification_logs WHERE channel='email'").fetchone()
        assert row["status"] == "failed"
        assert "SMTP unavailable" in row["error_message"]


def test_notification_log_page_requires_admin_or_manager(client, app):
    data = _login_and_csrf(client, app)
    response = client.get("/admin/notifications")
    assert response.status_code == 200


def test_visit_charge_cannot_be_confirmed_before_payment(client, app):
    with app.app_context():
        db = get_db()
        db.execute("UPDATE bookings SET home_visit_charge=299,visit_payment_status='pending' WHERE id=?", (app.config["TEST_BOOKING_ID"],))
        db.commit()
    data = _login_and_csrf(client, app)
    response = client.post(f"/admin/bookings/{app.config['TEST_BOOKING_ID']}/status", data={**data, "status": "Confirmed"})
    assert response.status_code == 302
    with app.app_context():
        row = get_db().execute("SELECT status,visit_payment_status FROM bookings WHERE id=?", (app.config["TEST_BOOKING_ID"],)).fetchone()
        assert row["status"] == "Pending"
        assert row["visit_payment_status"] == "pending"


def test_razorpay_webhook_signature_and_captured_payment(app, client):
    import hashlib, hmac, json
    app.config["RAZORPAY_WEBHOOK_SECRET"] = "test-webhook-secret"
    with app.app_context():
        db = get_db()
        bid = app.config["TEST_BOOKING_ID"]
        db.execute("UPDATE bookings SET home_visit_charge=299,visit_payment_status='pending',razorpay_order_id='order_test_1' WHERE id=?", (bid,))
        db.execute("INSERT INTO home_visit_payments(booking_id,order_id,amount_paise,currency,status,created_at,updated_at) VALUES(?,?,?,'INR','created',?,?)",
                   (bid, "order_test_1", 29900, now(), now()))
        db.commit()
    payload = {"event":"payment.captured","payload":{"payment":{"entity":{"id":"pay_test_1","order_id":"order_test_1","amount":29900,"currency":"INR","status":"captured"}}}}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(b"test-webhook-secret", raw, hashlib.sha256).hexdigest()
    response = client.post("/webhooks/razorpay", data=raw, content_type="application/json", headers={"X-Razorpay-Signature": signature, "X-Razorpay-Event-Id":"evt_test_1"})
    assert response.status_code == 200
    with app.app_context():
        row = get_db().execute("SELECT status,visit_payment_status,razorpay_payment_id FROM bookings WHERE id=?", (app.config["TEST_BOOKING_ID"],)).fetchone()
        assert row["status"] == "Confirmed"
        assert row["visit_payment_status"] == "paid"
        assert row["razorpay_payment_id"] == "pay_test_1"


def test_razorpay_webhook_rejects_bad_signature(app, client):
    app.config["RAZORPAY_WEBHOOK_SECRET"] = "test-webhook-secret"
    response = client.post("/webhooks/razorpay", data=b'{"event":"payment.captured"}', content_type="application/json", headers={"X-Razorpay-Signature":"bad"})
    assert response.status_code == 400


def test_staff_dispatch_requires_verified_payment(client, app):
    with app.app_context():
        db = get_db()
        bid = app.config["TEST_BOOKING_ID"]
        db.execute("UPDATE bookings SET home_visit_charge=299,visit_payment_status='pending' WHERE id=?", (bid,))
        tech_id = db.execute("INSERT INTO technicians(name,status,created_at,updated_at) VALUES('Test Tech','Active',?,?)", (now(), now())).lastrowid
        db.commit()
    data = _login_and_csrf(client, app)
    response = client.post(f"/admin/bookings/{app.config['TEST_BOOKING_ID']}/dispatch", data={**data, "technician_id": tech_id})
    assert response.status_code == 302
    with app.app_context():
        assert get_db().execute("SELECT dispatched_at FROM bookings WHERE id=?", (app.config["TEST_BOOKING_ID"],)).fetchone()[0] is None


def test_staff_dispatch_allowed_after_verified_payment(client, app):
    with app.app_context():
        db = get_db()
        bid = app.config["TEST_BOOKING_ID"]
        db.execute("UPDATE bookings SET home_visit_charge=299,visit_payment_status='paid',visit_paid_at=?,status='Confirmed' WHERE id=?", (now(), bid))
        tech_id = db.execute("INSERT INTO technicians(name,status,created_at,updated_at) VALUES('Test Tech','Active',?,?)", (now(), now())).lastrowid
        db.commit()
    data = _login_and_csrf(client, app)
    response = client.post(f"/admin/bookings/{app.config['TEST_BOOKING_ID']}/dispatch", data={**data, "technician_id": tech_id})
    assert response.status_code == 302
    with app.app_context():
        row = get_db().execute("SELECT dispatched_at,technician_id FROM bookings WHERE id=?", (app.config["TEST_BOOKING_ID"],)).fetchone()
        assert row["dispatched_at"] is not None
        assert row["technician_id"] == tech_id
        assert get_db().execute("SELECT technician_id FROM job_cards WHERE booking_id=?", (app.config["TEST_BOOKING_ID"],)).fetchone()[0] == tech_id


def test_webhook_amount_mismatch_cannot_unlock_dispatch(app, client):
    import hashlib, hmac, json
    app.config["RAZORPAY_WEBHOOK_SECRET"] = "test-webhook-secret"
    with app.app_context():
        db = get_db()
        bid = app.config["TEST_BOOKING_ID"]
        db.execute("UPDATE bookings SET home_visit_charge=299,visit_payment_status='pending',razorpay_order_id='order_wrong_amount' WHERE id=?", (bid,))
        db.execute("INSERT INTO home_visit_payments(booking_id,order_id,amount_paise,currency,status,created_at,updated_at) VALUES(?,?,?,'INR','created',?,?)", (bid, "order_wrong_amount", 29900, now(), now()))
        db.commit()
    payload = {"event":"payment.captured","payload":{"payment":{"entity":{"id":"pay_wrong_amount","order_id":"order_wrong_amount","amount":100,"currency":"INR","status":"captured"}}}}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(b"test-webhook-secret", raw, hashlib.sha256).hexdigest()
    response = client.post("/webhooks/razorpay", data=raw, content_type="application/json", headers={"X-Razorpay-Signature": signature})
    assert response.status_code == 400
    with app.app_context():
        row = get_db().execute("SELECT visit_payment_status FROM bookings WHERE id=?", (app.config["TEST_BOOKING_ID"],)).fetchone()
        assert row[0] == "pending"


def test_checkout_callback_requires_signature_and_captured_provider_status(client, app, monkeypatch):
    import hashlib, hmac
    import app.bookings.routes as routes
    with app.app_context():
        db = get_db()
        bid = app.config["TEST_BOOKING_ID"]
        db.execute("UPDATE bookings SET home_visit_charge=299,visit_payment_status='pending',razorpay_order_id='order_checkout_1',visit_payment_token='secure-test-token' WHERE id=?", (bid,))
        db.execute("INSERT INTO home_visit_payments(booking_id,order_id,amount_paise,currency,status,created_at,updated_at) VALUES(?,?,?,'INR','created',?,?)", (bid, "order_checkout_1", 29900, now(), now()))
        booking_no = db.execute("SELECT booking_no FROM bookings WHERE id=?", (bid,)).fetchone()[0]
        db.commit()
    class FakePaymentAPI:
        @staticmethod
        def fetch(payment_id):
            return {"id": payment_id, "order_id": "order_checkout_1", "amount": 29900, "currency": "INR", "status": "captured"}
    class FakeClient:
        payment = FakePaymentAPI()
    monkeypatch.setattr(routes, "_razorpay_client", lambda: FakeClient())
    secret = app.config["RAZORPAY_KEY_SECRET"]
    signature = hmac.new(secret.encode(), b"order_checkout_1|pay_checkout_1", hashlib.sha256).hexdigest()
    with client.session_transaction() as session:
        session["csrf_token"] = "payment-csrf"
    response = client.post(f"/booking/{booking_no}/visit-payment/secure-test-token/verify", data={
        "csrf_token": "payment-csrf", "razorpay_order_id": "order_checkout_1",
        "razorpay_payment_id": "pay_checkout_1", "razorpay_signature": signature,
    })
    assert response.status_code == 302
    with app.app_context():
        row = get_db().execute("SELECT visit_payment_status,razorpay_payment_id FROM bookings WHERE id=?", (app.config["TEST_BOOKING_ID"],)).fetchone()
        assert row["visit_payment_status"] == "paid"
        assert row["razorpay_payment_id"] == "pay_checkout_1"


def test_public_booking_requires_customer_address(client, app):
    with client.session_transaction() as session:
        session["csrf_token"] = "test-csrf"
    with app.app_context():
        service_id = get_db().execute("SELECT id FROM services LIMIT 1").fetchone()[0]
    response = client.post("/book", data={
        "csrf_token": "test-csrf", "name": "Address Test", "phone": "+919900001111",
        "car_model": "Test Car", "service_id": service_id, "date": "2099-01-01", "time": "10:00 AM",
    })
    assert response.status_code == 302
    with app.app_context():
        assert get_db().execute("SELECT id FROM customers WHERE phone=?", ("+919900001111",)).fetchone() is None


def test_booking_saves_customer_address_and_admin_can_see_it(client, app):
    with client.session_transaction() as session:
        session["csrf_token"] = "test-csrf"
    with app.app_context():
        service_id = get_db().execute("SELECT id FROM services LIMIT 1").fetchone()[0]
    response = client.post("/book", data={
        "csrf_token": "test-csrf", "name": "Address Test", "phone": "+919900001112",
        "address": "12 Main Road, Asansol, West Bengal - 713301", "car_model": "Test Car",
        "service_id": service_id, "date": "2099-01-01", "time": "10:00 AM",
    })
    assert response.status_code == 200
    assert b"12 Main Road, Asansol" in response.data
    with app.app_context():
        row = get_db().execute("SELECT address FROM customers WHERE phone=?", ("+919900001112",)).fetchone()
        assert row["address"] == "12 Main Road, Asansol, West Bengal - 713301"
