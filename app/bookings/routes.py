from datetime import datetime
import hashlib
import hmac
import json
import secrets
from flask import Blueprint, current_app, abort, flash, redirect, render_template, request, url_for
from app.auth.utils import login_required, role_required
from app.database import get_db, now
from app.notifications import notify_booking_status

bookings_bp = Blueprint("bookings", __name__)

BOOKING_STATUSES = ["Pending", "Confirmed", "In Progress", "Completed", "Cancelled"]
TIME_SLOTS = ["09:00 AM", "10:00 AM", "11:00 AM", "12:00 PM", "02:00 PM", "03:00 PM", "04:00 PM", "05:00 PM"]


def _booking_no(booking_id):
    return f"AC{datetime.now().strftime('%Y%m%d')}{booking_id:03d}"


@bookings_bp.get("/")
def main_home():
    return render_template("home.html", time_slots=TIME_SLOTS)


@bookings_bp.post("/book")
def book():
    d = request.form
    required = ["name", "phone", "address", "car_model", "service_id", "date", "time"]
    if any(not d.get(x, "").strip() for x in required):
        flash("Please complete all required booking details.", "error")
        return redirect(url_for("bookings.main_home") + "#booking")

    if len(d.get("address", "").strip()) > 500:
        flash("Address must be 500 characters or fewer.", "error")
        return redirect(url_for("bookings.main_home") + "#booking")

    service_id = d["service_id"].strip()
    db = get_db()
    service = db.execute("SELECT id FROM services WHERE id=? AND is_active=1", (service_id,)).fetchone()
    if not service:
        flash("Please select a valid service.", "error")
        return redirect(url_for("bookings.main_home") + "#booking")

    try:
        datetime.strptime(d["date"].strip(), "%Y-%m-%d")
    except ValueError:
        flash("Please select a valid appointment date.", "error")
        return redirect(url_for("bookings.main_home") + "#booking")

    if d["time"].strip() not in TIME_SLOTS:
        flash("Please select an available time slot.", "error")
        return redirect(url_for("bookings.main_home") + "#booking")

    preferred_contact = d.get("preferred_contact", "Phone").strip()
    if preferred_contact not in {"Phone", "Email", "WhatsApp"}:
        flash("Please choose a valid contact preference.", "error")
        return redirect(url_for("bookings.main_home") + "#booking")

    if d["date"].strip() < datetime.now().strftime("%Y-%m-%d"):
        flash("Appointment date cannot be in the past.", "error")
        return redirect(url_for("bookings.main_home") + "#booking")

    timestamp = now()
    phone = d["phone"].strip()
    customer = db.execute("SELECT id FROM customers WHERE phone=? ORDER BY id DESC LIMIT 1", (phone,)).fetchone()
    if customer:
        cid = customer["id"]
        db.execute("UPDATE customers SET name=?,email=?,address=?,updated_at=? WHERE id=?",
                   (d["name"].strip(), d.get("email", "").strip() or None, d.get("address", "").strip() or None, timestamp, cid))
    else:
        cur = db.execute("INSERT INTO customers(name,phone,email,address,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                         (d["name"].strip(), phone, d.get("email", "").strip() or None, d.get("address", "").strip() or None, timestamp, timestamp))
        cid = cur.lastrowid

    registration = d.get("registration", "").strip().upper() or None
    vehicle = None
    if registration:
        vehicle = db.execute("SELECT id FROM vehicles WHERE customer_id=? AND registration=?", (cid, registration)).fetchone()
    if vehicle:
        vid = vehicle["id"]
        db.execute("UPDATE vehicles SET brand=?,model=?,year=?,fuel=?,color=?,updated_at=? WHERE id=?",
                   (d.get("brand", "").strip() or None, d["car_model"].strip(), d.get("year", "").strip() or None,
                    d.get("fuel", "").strip() or None, d.get("color", "").strip() or None, timestamp, vid))
    else:
        cur = db.execute("""INSERT INTO vehicles(customer_id,registration,brand,model,year,fuel,color,created_at,updated_at)
                            VALUES(?,?,?,?,?,?,?,?,?)""",
                         (cid, registration, d.get("brand", "").strip() or None, d["car_model"].strip(),
                          d.get("year", "").strip() or None, d.get("fuel", "").strip() or None,
                          d.get("color", "").strip() or None, timestamp, timestamp))
        vid = cur.lastrowid

    duplicate = db.execute("""SELECT id FROM bookings
                              WHERE vehicle_id=? AND date=? AND time=?
                                AND status NOT IN ('Cancelled','Completed') LIMIT 1""",
                           (vid, d["date"].strip(), d["time"].strip())).fetchone()
    if duplicate:
        flash("That vehicle already has a booking for this date and time. Please choose another slot.", "error")
        return redirect(url_for("bookings.main_home") + "#booking")

    cur = db.execute("""INSERT INTO bookings
        (customer_id,vehicle_id,service_id,date,time,message,pickup_required,drop_required,preferred_contact,whatsapp_opt_in,status,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (cid, vid, service["id"], d["date"].strip(), d["time"].strip(), d.get("message", "").strip() or None,
         1 if d.get("pickup_required") else 0, 1 if d.get("drop_required") else 0,
         preferred_contact, 1 if d.get("whatsapp_opt_in") == "on" else 0,
         "Pending", timestamp, timestamp))
    bid = cur.lastrowid
    booking_no = _booking_no(bid)
    db.execute("UPDATE bookings SET booking_no=? WHERE id=?", (booking_no, bid))
    db.commit()
    return render_template("booking_confirmation.html", booking_no=booking_no, booking=db.execute(
        """SELECT b.*, c.name customer_name, c.address customer_address, v.registration, v.brand, v.model, s.name service_name
           FROM bookings b LEFT JOIN customers c ON c.id=b.customer_id
           LEFT JOIN vehicles v ON v.id=b.vehicle_id LEFT JOIN services s ON s.id=b.service_id WHERE b.id=?""", (bid,)).fetchone())


@bookings_bp.get("/admin/bookings")
@login_required
@role_required("admin", "manager", "receptionist")
def booking_list():
    db = get_db()
    status = request.args.get("status", "").strip()
    q = request.args.get("q", "").strip()
    sql = """SELECT b.*, c.name customer_name, c.phone, c.address customer_address, v.registration, v.brand, v.model,
                     s.name service_name
              FROM bookings b
              LEFT JOIN customers c ON c.id=b.customer_id
              LEFT JOIN vehicles v ON v.id=b.vehicle_id
              LEFT JOIN services s ON s.id=b.service_id
              WHERE 1=1"""
    params = []
    if status in BOOKING_STATUSES:
        sql += " AND b.status=?"; params.append(status)
    if q:
        sql += " AND (b.booking_no LIKE ? OR c.name LIKE ? OR c.phone LIKE ? OR c.address LIKE ? OR v.registration LIKE ? OR v.model LIKE ?)"
        params.extend([f"%{q}%"] * 6)
    sql += " ORDER BY b.date DESC,b.time DESC,b.id DESC"
    bookings = db.execute(sql, params).fetchall()
    technicians = db.execute("SELECT id,name,specialization FROM technicians WHERE status='Active' ORDER BY name").fetchall()
    return render_template("bookings.html", bookings=bookings, statuses=BOOKING_STATUSES, selected_status=status, q=q, technicians=technicians)


@bookings_bp.get("/admin/notifications")
@login_required
@role_required("admin", "manager")
def notification_logs():
    db = get_db()
    rows = db.execute(
        """SELECT id,booking_no,event_status,channel,recipient_masked,status,provider,
                  provider_message_id,provider_status,error_message,created_at,updated_at
           FROM notification_logs ORDER BY id DESC LIMIT 300"""
    ).fetchall()
    return render_template("notification_logs.html", notifications=rows)


@bookings_bp.post("/admin/bookings/<int:bid>/status")
@login_required
@role_required("admin", "manager", "receptionist")
def booking_status(bid):
    status = request.form.get("status", "")
    if status not in BOOKING_STATUSES:
        return ("Invalid booking status.", 400)
    db = get_db()
    booking = db.execute(
        """SELECT b.id,b.booking_no,b.status old_status,b.date,b.time,b.whatsapp_opt_in,
                  c.name customer_name,c.phone,c.email,v.registration,v.brand,v.model,s.name service_name
           FROM bookings b LEFT JOIN customers c ON c.id=b.customer_id
           LEFT JOIN vehicles v ON v.id=b.vehicle_id LEFT JOIN services s ON s.id=b.service_id
           WHERE b.id=?""", (bid,)
    ).fetchone()
    if not booking:
        return ("Booking not found.", 404)
    full_booking = db.execute("SELECT home_visit_charge,visit_payment_status FROM bookings WHERE id=?", (bid,)).fetchone()
    if status in {"Confirmed", "In Progress", "Completed"} and float(full_booking["home_visit_charge"] or 0) > 0 and full_booking["visit_payment_status"] != "paid":
        flash("A home-visit charge is set. The booking cannot be confirmed or progressed until Razorpay payment is verified.", "error")
        return redirect(request.referrer or url_for("bookings.booking_list"))
    if booking["old_status"] == status:
        flash("Booking status is unchanged; no notification was sent.", "info")
        return redirect(request.referrer or url_for("bookings.booking_list"))
    db.execute("UPDATE bookings SET status=?,updated_at=? WHERE id=?", (status, now(), bid))
    db.commit()  # Persist the business change before attempting external providers.
    try:
        notify_booking_status(dict(booking), status, app=current_app)
    except Exception:
        # Notification failures must never undo a successful booking status update.
        current_app.logger.exception("Unexpected booking notification error for booking %s", booking["booking_no"] or bid)
    flash("Booking status updated. Notification attempts are recorded in Notification Logs.", "success")
    return redirect(request.referrer or url_for("bookings.booking_list"))


# ---------- Razorpay advance payment for home visits ----------
def _razorpay_client():
    key_id = current_app.config.get("RAZORPAY_KEY_ID", "").strip()
    key_secret = current_app.config.get("RAZORPAY_KEY_SECRET", "").strip()
    if not key_id or not key_secret:
        raise RuntimeError("Razorpay is not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.")
    import razorpay
    return razorpay.Client(auth=(key_id, key_secret))


def _payment_booking(booking_no):
    return get_db().execute(
        """SELECT b.*,c.name customer_name,c.phone,c.email,v.registration,v.brand,v.model,s.name service_name
           FROM bookings b LEFT JOIN customers c ON c.id=b.customer_id
           LEFT JOIN vehicles v ON v.id=b.vehicle_id LEFT JOIN services s ON s.id=b.service_id
           WHERE b.booking_no=?""", (booking_no,)
    ).fetchone()


def _mark_visit_payment_paid(db, booking_id, order_id, payment_id, amount_paise, event_id=None, provider_status="captured"):
    """Idempotently mark payment paid only when order and expected amount match."""
    booking = db.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
    if not booking or booking["razorpay_order_id"] != order_id:
        return False
    expected_paise = int(round(float(booking["home_visit_charge"] or 0) * 100))
    if expected_paise <= 0 or int(amount_paise) != expected_paise:
        return False
    if booking["visit_payment_status"] == "paid":
        # Duplicate webhooks/callbacks are safe; never create a second payment record.
        return booking["razorpay_payment_id"] == payment_id
    stamp = now()
    db.execute(
        """UPDATE bookings SET visit_payment_status='paid',razorpay_payment_id=?,visit_paid_at=?,
           status=CASE WHEN status='Pending' THEN 'Confirmed' ELSE status END,updated_at=? WHERE id=?""",
        (payment_id, stamp, stamp, booking_id),
    )
    db.execute(
        """UPDATE home_visit_payments SET payment_id=?,status='captured',webhook_event_id=COALESCE(?,webhook_event_id),
           raw_provider_status=?,updated_at=? WHERE order_id=?""",
        (payment_id, event_id, provider_status, stamp, order_id),
    )
    db.commit()
    return True


@bookings_bp.post("/admin/bookings/<int:bid>/visit-charge")
@login_required
@role_required("admin", "manager")
def set_home_visit_charge(bid):
    db = get_db()
    booking = db.execute("SELECT id,booking_no,status,home_visit_charge,visit_payment_status,razorpay_order_id,dispatched_at FROM bookings WHERE id=?", (bid,)).fetchone()
    if not booking:
        abort(404)
    if booking["status"] == "Cancelled":
        flash("A cancelled booking cannot receive a new visit payment order.", "error")
        return redirect(request.referrer or url_for("bookings.booking_list"))
    if booking["visit_payment_status"] == "paid" or booking["dispatched_at"]:
        flash("The visit charge cannot be changed after payment or dispatch.", "error")
        return redirect(request.referrer or url_for("bookings.booking_list"))
    try:
        charge = round(float(request.form.get("home_visit_charge", "")), 2)
        if charge <= 0 or charge > 100000:
            raise ValueError
    except (TypeError, ValueError):
        flash("Enter a valid visit charge greater than ₹0 and no more than ₹1,00,000.", "error")
        return redirect(request.referrer or url_for("bookings.booking_list"))
    if not current_app.config.get("RAZORPAY_KEY_ID") or not current_app.config.get("RAZORPAY_KEY_SECRET"):
        flash("Razorpay is not configured. Set test-mode API keys before creating a payment order.", "error")
        return redirect(request.referrer or url_for("bookings.booking_list"))
    try:
        receipt = f"visit_{booking['id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        if booking["razorpay_order_id"] and booking["visit_payment_status"] == "pending":
            flash("A payment order already exists for this booking. Use its existing payment link; do not create duplicate orders.", "info")
            return redirect(request.referrer or url_for("bookings.booking_list"))
        order = _razorpay_client().order.create(data={
            "amount": int(round(charge * 100)), "currency": "INR", "receipt": receipt,
            "notes": {"booking_no": booking["booking_no"], "purpose": "home_visit_charge"}
        })
        order_id = order.get("id")
        if not order_id:
            raise RuntimeError("Razorpay did not return an order ID.")
        stamp = now()
        payment_token = secrets.token_urlsafe(32)
        db.execute("""UPDATE bookings SET home_visit_charge=?,visit_payment_status='pending',razorpay_order_id=?,
                      visit_payment_token=?,razorpay_payment_id=NULL,visit_paid_at=NULL,status='Pending',updated_at=? WHERE id=?""",
                   (charge, order_id, payment_token, stamp, bid))
        db.execute("""INSERT INTO home_visit_payments(booking_id,order_id,amount_paise,currency,status,created_at,updated_at)
                      VALUES(?,?,?,'INR','created',?,?)""",
                   (bid, order_id, int(round(charge * 100)), stamp, stamp))
        db.commit()
        payment_url = url_for("bookings.public_visit_payment", booking_no=booking["booking_no"], token=payment_token, _external=True)
        fresh = _payment_booking(booking["booking_no"])
        message_booking = dict(fresh)
        message_booking["payment_url"] = payment_url
        try:
            notify_booking_status(message_booking, f"Visit payment required — ₹{charge:.2f}", app=current_app)
        except Exception:
            current_app.logger.exception("Visit payment notification failed for %s", booking["booking_no"])
        flash(f"Visit charge set to ₹{charge:.2f}. Payment link: {payment_url}", "success")
    except Exception as exc:
        db.rollback()
        current_app.logger.warning("Razorpay order creation failed for booking %s: %s", booking["booking_no"], type(exc).__name__)
        flash("Could not create a Razorpay order. Check test API credentials and server logs.", "error")
    return redirect(request.referrer or url_for("bookings.booking_list"))


@bookings_bp.get("/booking/<booking_no>/visit-payment/<token>")
def public_visit_payment(booking_no, token):
    booking = _payment_booking(booking_no)
    if not booking or not booking["visit_payment_token"] or not hmac.compare_digest(str(booking["visit_payment_token"]), str(token)):
        abort(404)
    if booking["visit_payment_status"] == "paid":
        return render_template("visit_payment.html", booking=booking, paid=True, key_id="", amount=0)
    if booking["status"] == "Cancelled" or not booking["razorpay_order_id"] or booking["visit_payment_status"] != "pending":
        return render_template("visit_payment.html", booking=booking, paid=False, unavailable=True, key_id="", amount=0), 409
    if not current_app.config.get("RAZORPAY_KEY_ID"):
        return render_template("visit_payment.html", booking=booking, paid=False, unavailable=True, key_id="", amount=0), 503
    return render_template("visit_payment.html", booking=booking, paid=False, unavailable=False,
                           key_id=current_app.config["RAZORPAY_KEY_ID"], amount=int(round(float(booking["home_visit_charge"])*100)))


@bookings_bp.post("/booking/<booking_no>/visit-payment/<token>/verify")
def verify_visit_payment(booking_no, token):
    db = get_db()
    booking = _payment_booking(booking_no)
    if not booking or not booking["visit_payment_token"] or not hmac.compare_digest(str(booking["visit_payment_token"]), str(token)):
        abort(404)
    if booking["visit_payment_status"] == "paid":
        flash("Visit payment is already verified.", "success")
        return redirect(url_for("bookings.public_visit_payment", booking_no=booking_no, token=token))
    order_id = (request.form.get("razorpay_order_id") or "").strip()
    payment_id = (request.form.get("razorpay_payment_id") or "").strip()
    signature = (request.form.get("razorpay_signature") or "").strip()
    if not order_id or not payment_id or not signature or order_id != booking["razorpay_order_id"]:
        abort(400, description="Invalid Razorpay payment response.")
    secret = current_app.config.get("RAZORPAY_KEY_SECRET", "")
    expected = hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(expected, signature):
        current_app.logger.warning("Invalid Razorpay checkout signature for booking %s", booking_no)
        abort(400, description="Payment signature verification failed.")
    try:
        payment = _razorpay_client().payment.fetch(payment_id)
    except Exception:
        current_app.logger.exception("Could not fetch Razorpay payment status for booking %s", booking_no)
        flash("Payment response received, but payment status could not be verified yet. Please refresh shortly.", "warning")
        return redirect(url_for("bookings.public_visit_payment", booking_no=booking_no, token=token))
    if payment.get("order_id") != order_id or payment.get("currency") != "INR" or int(payment.get("amount", 0)) != int(round(float(booking["home_visit_charge"])*100)) or payment.get("status") != "captured":
        flash("Razorpay has not confirmed a captured payment for this exact visit charge. Staff cannot be dispatched yet.", "error")
        return redirect(url_for("bookings.public_visit_payment", booking_no=booking_no, token=token))
    if not _mark_visit_payment_paid(db, booking["id"], order_id, payment_id, payment.get("amount", 0), provider_status=payment.get("status", "captured")):
        abort(400, description="Payment does not match this booking's expected visit charge.")
    flash("Visit payment verified successfully. The garage can now arrange the visit.", "success")
    return redirect(url_for("bookings.public_visit_payment", booking_no=booking_no, token=token))


@bookings_bp.post("/webhooks/razorpay")
def razorpay_webhook():
    webhook_secret = current_app.config.get("RAZORPAY_WEBHOOK_SECRET", "")
    signature = request.headers.get("X-Razorpay-Signature", "")
    raw_body = request.get_data(cache=True, as_text=False)
    if not webhook_secret or not signature:
        return ("Webhook not configured.", 400)
    expected = hmac.new(webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        current_app.logger.warning("Rejected Razorpay webhook: signature mismatch")
        return ("Invalid webhook signature.", 400)
    try:
        event = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ("Invalid JSON payload.", 400)
    event_name = event.get("event")
    if event_name not in {"payment.captured", "payment.failed"}:
        return ("Event ignored.", 200)
    payload = event.get("payload", {}).get("payment", {}).get("entity", {})
    order_id = payload.get("order_id")
    payment_id = payload.get("id")
    amount = payload.get("amount")
    expected_provider_status = "captured" if event_name == "payment.captured" else "failed"
    if not order_id or not payment_id or amount is None or payload.get("status") != expected_provider_status or payload.get("currency") != "INR":
        return ("Incomplete payment event.", 400)
    db = get_db()
    row = db.execute("SELECT id,home_visit_charge,visit_payment_status FROM bookings WHERE razorpay_order_id=?", (order_id,)).fetchone()
    if not row:
        return ("Unknown order.", 404)
    expected_amount = int(round(float(row["home_visit_charge"] or 0) * 100))
    if expected_amount <= 0 or int(amount) != expected_amount:
        return ("Payment amount mismatch.", 400)
    event_id = request.headers.get("X-Razorpay-Event-Id")
    if event_name == "payment.failed":
        if row["visit_payment_status"] != "paid":
            stamp = now()
            db.execute("UPDATE bookings SET visit_payment_status='failed',updated_at=? WHERE id=?", (stamp, row["id"]))
            db.execute("UPDATE home_visit_payments SET status='failed',payment_id=?,webhook_event_id=COALESCE(?,webhook_event_id),raw_provider_status='failed',updated_at=? WHERE order_id=?",
                       (payment_id, event_id, stamp, order_id))
            db.commit()
        return ("ok", 200)
    if not _mark_visit_payment_paid(db, row["id"], order_id, payment_id, amount, event_id=event_id, provider_status="captured"):
        return ("Payment amount or order mismatch.", 400)
    return ("ok", 200)


@bookings_bp.post("/admin/bookings/<int:bid>/dispatch")
@login_required
@role_required("admin", "manager")
def dispatch_home_visit(bid):
    db = get_db()
    booking = db.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone()
    if not booking:
        abort(404)
    if booking["status"] == "Cancelled":
        flash("A cancelled booking cannot be dispatched.", "error")
        return redirect(request.referrer or url_for("bookings.booking_list"))
    if float(booking["home_visit_charge"] or 0) <= 0 or booking["visit_payment_status"] != "paid":
        flash("Staff cannot be dispatched until the fixed visit charge is paid and verified.", "error")
        return redirect(request.referrer or url_for("bookings.booking_list"))
    technician_id = request.form.get("technician_id", type=int)
    tech = db.execute("SELECT id FROM technicians WHERE id=? AND status='Active'", (technician_id,)).fetchone() if technician_id else None
    if not tech:
        flash("Select an active technician before dispatching staff.", "error")
        return redirect(request.referrer or url_for("bookings.booking_list"))
    stamp = now()
    db.execute("UPDATE bookings SET technician_id=?,dispatched_at=?,status='Confirmed',updated_at=? WHERE id=?",
               (technician_id, stamp, stamp, bid))
    job = db.execute("SELECT id FROM job_cards WHERE booking_id=?", (bid,)).fetchone()
    if job:
        db.execute("UPDATE job_cards SET technician_id=?,updated_at=? WHERE id=?", (technician_id, stamp, job["id"]))
    elif booking["customer_id"] and booking["vehicle_id"]:
        # Dispatch creates the inspection job card so the assigned technician can record findings.
        db.execute("""INSERT INTO job_cards(booking_id,customer_id,vehicle_id,complaint,technician_id,status,created_at,updated_at)
                      VALUES(?,?,?,?,?,'Open',?,?)""",
                   (bid, booking["customer_id"], booking["vehicle_id"], booking["message"], technician_id, stamp, stamp))
    db.commit()
    flash("Staff assigned and dispatched. An inspection job card is ready for the technician.", "success")
    return redirect(request.referrer or url_for("bookings.booking_list"))
