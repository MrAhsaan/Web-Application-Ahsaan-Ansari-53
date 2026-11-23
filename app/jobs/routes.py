from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from app.auth.utils import login_required, role_required
from app.database import get_db, now

jobs_bp = Blueprint("jobs", __name__)
JOB_STATUSES = ("Open", "In Progress", "Ready", "Closed")
ITEM_TYPES = ("service", "part", "labor", "other")


def money(value):
    try:
        value = float(value or 0)
        return max(0.0, value)
    except (TypeError, ValueError):
        return 0.0


def integer(value):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def load_form_data(db):
    return {
        "customers": db.execute("SELECT * FROM customers ORDER BY name").fetchall(),
        "technicians": db.execute("SELECT * FROM technicians WHERE status='Active' ORDER BY name").fetchall(),
        "services": db.execute("SELECT * FROM services WHERE is_active=1 ORDER BY name").fetchall(),
        "bookings": db.execute(
            """SELECT b.id,b.booking_no,b.date,b.time,b.status,c.name customer_name,v.registration,v.brand,v.model,s.name service_name
               FROM bookings b
               LEFT JOIN customers c ON c.id=b.customer_id
               LEFT JOIN vehicles v ON v.id=b.vehicle_id
               LEFT JOIN services s ON s.id=b.service_id
               WHERE b.status != 'Cancelled' AND NOT EXISTS
                     (SELECT 1 FROM job_cards j WHERE j.booking_id=b.id)
               ORDER BY b.date DESC,b.time DESC,b.id DESC"""
        ).fetchall(),
    }


@jobs_bp.get("/admin/jobs")
@login_required
@role_required("admin", "manager", "technician")
def job_list():
    db = get_db()
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    where, params = [], []
    if q:
        like = f"%{q}%"
        where.append("(CAST(j.id AS TEXT) LIKE ? OR c.name LIKE ? OR c.phone LIKE ? OR v.registration LIKE ? OR v.model LIKE ? OR t.name LIKE ?)")
        params.extend([like] * 6)
    if status in JOB_STATUSES:
        where.append("j.status=?")
        params.append(status)
    sql = """SELECT j.id,j.status,j.created_at,j.updated_at,c.name customer_name,c.phone,
                    v.registration,v.brand,v.model,t.name technician_name,
                    COALESCE(SUM(ji.total),0) total
             FROM job_cards j
             JOIN customers c ON c.id=j.customer_id
             JOIN vehicles v ON v.id=j.vehicle_id
             LEFT JOIN technicians t ON t.id=j.technician_id
             LEFT JOIN job_items ji ON ji.job_card_id=j.id"""
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " GROUP BY j.id ORDER BY j.id DESC"
    jobs = db.execute(sql, params).fetchall()
    counts = {s: db.execute("SELECT COUNT(*) FROM job_cards WHERE status=?", (s,)).fetchone()[0] for s in JOB_STATUSES}
    return render_template("jobs.html", jobs=jobs, counts=counts, statuses=JOB_STATUSES, q=q, status=status)


@jobs_bp.route("/admin/job/new", methods=["GET", "POST"])
@login_required
@role_required("admin", "manager", "technician")
def job_new():
    db = get_db()
    data = load_form_data(db)
    vehicles = db.execute("SELECT * FROM vehicles ORDER BY registration,model").fetchall()

    if request.method == "POST":
        d = request.form
        customer_id = integer(d.get("customer_id"))
        vehicle_id = integer(d.get("vehicle_id"))
        booking_id = integer(d.get("booking_id"))
        technician_id = integer(d.get("technician_id"))
        status = d.get("status", "Open")

        if status not in JOB_STATUSES:
            abort(400, description="Invalid job status.")
        vehicle = db.execute("SELECT id FROM vehicles WHERE id=? AND customer_id=?", (vehicle_id, customer_id)).fetchone()
        if not customer_id or not vehicle:
            flash("Please select a vehicle that belongs to the selected customer.", "error")
            return render_template("job_form.html", vehicles=vehicles, **data)

        if booking_id:
            booking = db.execute("SELECT customer_id,vehicle_id FROM bookings WHERE id=?", (booking_id,)).fetchone()
            if not booking or booking["customer_id"] != customer_id or booking["vehicle_id"] != vehicle_id:
                flash("The selected booking does not belong to the selected customer and vehicle.", "error")
                return render_template("job_form.html", vehicles=vehicles, **data)

        timestamp = now()
        try:
            cur = db.execute(
                """INSERT INTO job_cards
                   (booking_id,customer_id,vehicle_id,complaint,diagnosis,work_done,technician_id,odometer,status,notes,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (booking_id, customer_id, vehicle_id, d.get("complaint", "").strip(), d.get("diagnosis", "").strip(),
                 d.get("work_done", "").strip(), technician_id, integer(d.get("odometer")), status,
                 d.get("notes", "").strip(), timestamp, timestamp),
            )
            jid = cur.lastrowid
            _replace_items(db, jid, request.form, timestamp)
            if booking_id and status in {"In Progress", "Ready", "Closed"}:
                db.execute("UPDATE bookings SET status=?,updated_at=? WHERE id=?", ("In Progress", timestamp, booking_id))
            db.commit()
        except Exception:
            db.rollback()
            flash("Could not create the job card. The booking may already have a job card.", "error")
            return render_template("job_form.html", vehicles=vehicles, **data)
        flash(f"Job Card #{jid} created.", "success")
        return redirect(url_for("jobs.job_view", jid=jid))

    return render_template("job_form.html", vehicles=vehicles, **data)


def _replace_items(db, jid, form, timestamp):
    db.execute("DELETE FROM job_items WHERE job_card_id=?", (jid,))
    service_ids = form.getlist("item_service_id[]")
    types = form.getlist("item_type[]")
    descriptions = form.getlist("item_description[]")
    quantities = form.getlist("item_quantity[]")
    prices = form.getlist("item_unit_price[]")
    rows = max(len(types), len(descriptions), len(prices), len(service_ids))
    for i in range(rows):
        item_type = (types[i].strip().lower() if i < len(types) else "other")
        description = (descriptions[i].strip() if i < len(descriptions) else "")
        if not description or item_type not in ITEM_TYPES:
            continue
        quantity = money(quantities[i]) if i < len(quantities) else 1
        unit_price = money(prices[i]) if i < len(prices) else 0
        if quantity <= 0:
            continue
        service_id = integer(service_ids[i]) if i < len(service_ids) and service_ids[i] else None
        if service_id:
            exists = db.execute("SELECT id FROM services WHERE id=? AND is_active=1", (service_id,)).fetchone()
            if not exists:
                service_id = None
        db.execute(
            """INSERT INTO job_items(job_card_id,service_id,item_type,description,quantity,unit_price,total,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (jid, service_id, item_type, description, quantity, unit_price, round(quantity * unit_price, 2), timestamp, timestamp),
        )


@jobs_bp.route("/admin/job/<int:jid>", methods=["GET", "POST"])
@login_required
@role_required("admin", "manager", "technician")
def job_view(jid):
    db = get_db()
    job = db.execute(
        """SELECT j.*,c.name customer_name,c.phone,c.email,v.registration,v.brand,v.model,v.year,v.fuel,v.color,v.vin,
                  t.name technician_name,b.booking_no,b.date booking_date,b.time booking_time
           FROM job_cards j
           JOIN customers c ON c.id=j.customer_id
           JOIN vehicles v ON v.id=j.vehicle_id
           LEFT JOIN technicians t ON t.id=j.technician_id
           LEFT JOIN bookings b ON b.id=j.booking_id
           WHERE j.id=?""", (jid,)
    ).fetchone()
    if not job:
        abort(404)

    if request.method == "POST":
        d = request.form
        technician_id = integer(d.get("technician_id"))
        odometer = integer(d.get("odometer"))
        status = d.get("status", "Open")
        if status not in JOB_STATUSES:
            abort(400, description="Invalid job status.")
        timestamp = now()
        try:
            db.execute(
                """UPDATE job_cards SET complaint=?,diagnosis=?,work_done=?,technician_id=?,odometer=?,status=?,notes=?,updated_at=?
                   WHERE id=?""",
                (d.get("complaint", "").strip(), d.get("diagnosis", "").strip(), d.get("work_done", "").strip(),
                 technician_id, odometer, status, d.get("notes", "").strip(), timestamp, jid),
            )
            _replace_items(db, jid, request.form, timestamp)
            if job["booking_id"] and status != "Closed":
                db.execute("UPDATE bookings SET status=?,updated_at=? WHERE id=?", ("In Progress", timestamp, job["booking_id"]))
            elif job["booking_id"] and status == "Closed":
                db.execute("UPDATE bookings SET status=?,updated_at=? WHERE id=?", ("Completed", timestamp, job["booking_id"]))
            db.commit()
        except Exception:
            db.rollback()
            flash("Could not update the job card.", "error")
        else:
            flash("Job Card updated.", "success")
        return redirect(url_for("jobs.job_view", jid=jid))

    items = db.execute(
        """SELECT ji.*,s.name service_name FROM job_items ji
           LEFT JOIN services s ON s.id=ji.service_id WHERE ji.job_card_id=? ORDER BY ji.id""", (jid,)
    ).fetchall()
    subtotal = round(sum(float(i["total"] or 0) for i in items), 2)
    technicians = db.execute("SELECT * FROM technicians WHERE status='Active' OR id=? ORDER BY name", (job["technician_id"],)).fetchall()
    services = db.execute("SELECT * FROM services WHERE is_active=1 ORDER BY name").fetchall()
    invoice = db.execute("SELECT * FROM invoices WHERE job_card_id=?", (jid,)).fetchone()
    payments = db.execute("SELECT * FROM payments WHERE invoice_id=? ORDER BY payment_date DESC,id DESC", (invoice["id"],)).fetchall() if invoice else []
    return render_template("job_view.html", job=job, items=items, subtotal=subtotal, invoice=invoice,
                           payments=payments, technicians=technicians, services=services,
                           statuses=JOB_STATUSES, item_types=ITEM_TYPES)
