import re
from sqlite3 import IntegrityError

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.auth.utils import login_required, role_required
from app.database import get_db, now

customers_bp = Blueprint("customers", __name__)


def clean_phone(value):
    return re.sub(r"[^0-9+ -]", "", (value or "").strip())


def clean_registration(value):
    value = re.sub(r"\s+", "", (value or "").strip().upper())
    return value or None


def clean_vin(value):
    value = re.sub(r"\s+", "", (value or "").strip().upper())
    return value or None


def parse_year(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        year = int(value)
    except ValueError:
        raise ValueError("Year must be a valid number.")
    if year < 1900 or year > 2100:
        raise ValueError("Please enter a valid vehicle year.")
    return year


def parse_vehicle_form(form):
    registration = clean_registration(form.get("registration"))
    brand = form.get("brand", "").strip()
    model = form.get("model", "").strip()
    fuel = form.get("fuel", "").strip()
    color = form.get("color", "").strip()
    vin = clean_vin(form.get("vin"))
    notes = form.get("notes", "").strip()
    year = parse_year(form.get("year"))
    if not model:
        raise ValueError("Vehicle model is required.")
    return registration, brand, model, year, fuel, color, vin, notes


@customers_bp.route("/admin/customers", methods=["GET", "POST"])
@login_required
@role_required("admin", "manager", "receptionist")
def customers():
    db = get_db()
    if request.method == "POST":
        d = request.form
        name = d.get("name", "").strip()
        phone = clean_phone(d.get("phone"))
        email = d.get("email", "").strip() or None
        address = d.get("address", "").strip() or None
        notes = d.get("notes", "").strip() or None
        if not name or not phone:
            flash("Customer name and phone are required.", "error")
        else:
            try:
                db.execute(
                    """INSERT INTO customers
                   (name, phone, email, address, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (name, phone, email, address, notes, now(), now()),
                )
                db.commit()
                flash("Customer added successfully.", "success")
                return redirect(url_for("customers.customers"))
            except IntegrityError:
                db.rollback()
                flash("That email address is already assigned to another customer.", "error")

    search = request.args.get("q", "").strip()
    if search:
        like = f"%{search}%"
        rows = db.execute(
            """SELECT c.*,
                      COUNT(DISTINCT v.id) AS vehicle_count
               FROM customers c
               LEFT JOIN vehicles v ON v.customer_id = c.id
               WHERE c.name LIKE ? OR c.phone LIKE ? OR COALESCE(c.email,'') LIKE ?
               GROUP BY c.id
               ORDER BY c.id DESC""",
            (like, like, like),
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT c.*,
                      COUNT(DISTINCT v.id) AS vehicle_count
               FROM customers c
               LEFT JOIN vehicles v ON v.customer_id = c.id
               GROUP BY c.id
               ORDER BY c.id DESC"""
        ).fetchall()
    return render_template("customers.html", customers=rows, search=search)


@customers_bp.route("/admin/customers/<int:cid>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin", "manager", "receptionist")
def customer_edit(cid):
    db = get_db()
    customer = db.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()
    if not customer:
        abort(404)

    if request.method == "POST":
        d = request.form
        name = d.get("name", "").strip()
        phone = clean_phone(d.get("phone"))
        if not name or not phone:
            flash("Customer name and phone are required.", "error")
        else:
            db.execute(
                """UPDATE customers
                   SET name=?, phone=?, email=?, address=?, notes=?, updated_at=?
                   WHERE id=?""",
                (
                    name,
                    phone,
                    d.get("email", "").strip() or None,
                    d.get("address", "").strip() or None,
                    d.get("notes", "").strip() or None,
                    now(),
                    cid,
                ),
            )
            db.commit()
            flash("Customer details updated.", "success")
            return redirect(url_for("customers.customer_detail", cid=cid))

    return render_template("customer_edit.html", customer=customer)


@customers_bp.route("/admin/customers/<int:cid>/delete", methods=["POST"])
@login_required
@role_required("admin", "manager", "receptionist")
def customer_delete(cid):
    db = get_db()
    customer = db.execute("SELECT id FROM customers WHERE id=?", (cid,)).fetchone()
    if not customer:
        abort(404)

    dependent = db.execute(
        """SELECT
             EXISTS(SELECT 1 FROM job_cards WHERE customer_id=?) AS jobs,
             EXISTS(SELECT 1 FROM estimates WHERE customer_id=?) AS estimates,
             EXISTS(SELECT 1 FROM invoices i JOIN job_cards j ON j.id=i.job_card_id WHERE j.customer_id=?) AS invoices
        """,
        (cid, cid, cid),
    ).fetchone()
    if dependent["jobs"] or dependent["estimates"] or dependent["invoices"]:
        flash("This customer cannot be deleted because service history exists. Edit the customer instead.", "error")
        return redirect(url_for("customers.customer_detail", cid=cid))

    try:
        db.execute("DELETE FROM customers WHERE id=?", (cid,))
        db.commit()
        flash("Customer deleted.", "success")
    except IntegrityError:
        db.rollback()
        flash("Customer cannot be deleted because related records exist.", "error")
    return redirect(url_for("customers.customers"))


@customers_bp.route("/admin/customers/<int:cid>", methods=["GET"])
@login_required
@role_required("admin", "manager", "receptionist")
def customer_detail(cid):
    db = get_db()
    customer = db.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()
    if not customer:
        abort(404)

    vehicles = db.execute(
        """SELECT v.*,
                  EXISTS(SELECT 1 FROM job_cards j WHERE j.vehicle_id=v.id) AS has_jobs
           FROM vehicles v
           WHERE v.customer_id=?
           ORDER BY v.id DESC""",
        (cid,),
    ).fetchall()
    jobs = db.execute(
        """SELECT j.id,j.status,j.created_at,v.registration,v.brand,v.model,
                  COALESCE((SELECT SUM(total) FROM job_items WHERE job_card_id=j.id),0) AS total
           FROM job_cards j
           LEFT JOIN vehicles v ON v.id=j.vehicle_id
           WHERE j.customer_id=? ORDER BY j.id DESC""",
        (cid,),
    ).fetchall()
    booking_count = db.execute(
        "SELECT COUNT(*) AS n FROM bookings WHERE customer_id=?", (cid,)
    ).fetchone()["n"]
    return render_template(
        "customer.html",
        customer=customer,
        vehicles=vehicles,
        jobs=jobs,
        booking_count=booking_count,
    )


@customers_bp.route("/admin/customers/<int:cid>/vehicles/add", methods=["POST"])
@login_required
@role_required("admin", "manager", "receptionist")
def vehicle_add(cid):
    db = get_db()
    if not db.execute("SELECT 1 FROM customers WHERE id=?", (cid,)).fetchone():
        abort(404)
    try:
        data = parse_vehicle_form(request.form)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("customers.customer_detail", cid=cid))

    try:
        db.execute(
            """INSERT INTO vehicles
               (customer_id,registration,brand,model,year,fuel,color,vin,notes,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (cid, *data, now(), now()),
        )
        db.commit()
        flash("Vehicle added successfully.", "success")
    except IntegrityError:
        db.rollback()
        flash("Registration number or VIN is already in use.", "error")
    return redirect(url_for("customers.customer_detail", cid=cid))


@customers_bp.route("/admin/vehicles/<int:vid>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin", "manager", "receptionist")
def vehicle_edit(vid):
    db = get_db()
    vehicle = db.execute(
        """SELECT v.*, c.name AS customer_name
           FROM vehicles v JOIN customers c ON c.id=v.customer_id
           WHERE v.id=?""",
        (vid,),
    ).fetchone()
    if not vehicle:
        abort(404)

    if request.method == "POST":
        try:
            data = parse_vehicle_form(request.form)
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            try:
                db.execute(
                    """UPDATE vehicles
                       SET registration=?, brand=?, model=?, year=?, fuel=?, color=?, vin=?, notes=?, updated_at=?
                       WHERE id=?""",
                    (*data, now(), vid),
                )
                db.commit()
                flash("Vehicle details updated.", "success")
                return redirect(url_for("customers.customer_detail", cid=vehicle["customer_id"]))
            except IntegrityError:
                db.rollback()
                flash("Registration number or VIN is already in use.", "error")

    return render_template("vehicle_edit.html", vehicle=vehicle)


@customers_bp.route("/admin/vehicles/<int:vid>/delete", methods=["POST"])
@login_required
@role_required("admin", "manager", "receptionist")
def vehicle_delete(vid):
    db = get_db()
    vehicle = db.execute("SELECT id,customer_id FROM vehicles WHERE id=?", (vid,)).fetchone()
    if not vehicle:
        abort(404)

    has_history = db.execute(
        """SELECT
             EXISTS(SELECT 1 FROM job_cards WHERE vehicle_id=?) AS jobs,
             EXISTS(SELECT 1 FROM estimates WHERE vehicle_id=?) AS estimates
        """,
        (vid, vid),
    ).fetchone()
    if has_history["jobs"] or has_history["estimates"]:
        flash("This vehicle cannot be deleted because service history exists.", "error")
        return redirect(url_for("customers.customer_detail", cid=vehicle["customer_id"]))

    try:
        db.execute("DELETE FROM vehicles WHERE id=?", (vid,))
        db.commit()
        flash("Vehicle deleted.", "success")
    except IntegrityError:
        db.rollback()
        flash("Vehicle cannot be deleted because related records exist.", "error")
    return redirect(url_for("customers.customer_detail", cid=vehicle["customer_id"]))
