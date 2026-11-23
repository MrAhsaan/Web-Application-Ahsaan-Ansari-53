from datetime import date, timedelta
from flask import Blueprint, render_template, request, Response
from app.auth.utils import login_required, role_required
from app.database import get_db


dashboard_bp = Blueprint("dashboard", __name__)


def _date_range():
    today = date.today()
    period = request.args.get("period", "30")
    if period == "7":
        start = today - timedelta(days=6)
    elif period == "90":
        start = today - timedelta(days=89)
    elif period == "365":
        start = today - timedelta(days=364)
    else:
        period = "30"
        start = today - timedelta(days=29)
    return period, start.isoformat(), today.isoformat()


@dashboard_bp.get("/admin")
@login_required
def dashboard():
    db = get_db()
    today = date.today().isoformat()
    stats = {
        "customers": db.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
        "vehicles": db.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0],
        "bookings": db.execute("SELECT COUNT(*) FROM bookings").fetchone()[0],
        "open_jobs": db.execute("SELECT COUNT(*) FROM job_cards WHERE status != 'Closed'").fetchone()[0],
        "revenue": db.execute("SELECT COALESCE(SUM(amount),0) FROM payments").fetchone()[0],
        "today_collection": db.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE payment_date=?", (today,)).fetchone()[0],
        "outstanding": db.execute("SELECT COALESCE(SUM(total-paid_amount),0) FROM invoices WHERE total > paid_amount").fetchone()[0],
    }
    bookings = db.execute("""SELECT b.*, c.name customer_name, c.phone,
        v.registration, v.brand, v.model, s.name service_name
        FROM bookings b
        LEFT JOIN customers c ON c.id=b.customer_id
        LEFT JOIN vehicles v ON v.id=b.vehicle_id
        LEFT JOIN services s ON s.id=b.service_id
        ORDER BY b.date DESC,b.time DESC,b.id DESC LIMIT 12""").fetchall()

    status_rows = db.execute("SELECT status, COUNT(*) count FROM bookings GROUP BY status ORDER BY count DESC").fetchall()
    payment_rows = db.execute("SELECT payment_method, COALESCE(SUM(amount),0) total FROM payments GROUP BY payment_method ORDER BY total DESC").fetchall()
    top_services = db.execute("""SELECT COALESCE(s.name, ji.description) name,
        COUNT(ji.id) jobs, COALESCE(SUM(ji.total),0) revenue
        FROM job_items ji LEFT JOIN services s ON s.id=ji.service_id
        GROUP BY COALESCE(s.name, ji.description) ORDER BY revenue DESC LIMIT 5""").fetchall()
    return render_template("dashboard.html", stats=stats, bookings=bookings,
                           status_rows=status_rows, payment_rows=payment_rows, top_services=top_services)


@dashboard_bp.get("/admin/reports")
@login_required
@role_required("admin", "manager")
def reports():
    db = get_db()
    period, start, end = _date_range()
    summary = db.execute("""SELECT
        (SELECT COUNT(*) FROM bookings WHERE date BETWEEN ? AND ?) bookings,
        (SELECT COUNT(*) FROM job_cards WHERE date(created_at) BETWEEN ? AND ?) jobs,
        (SELECT COUNT(*) FROM customers WHERE date(created_at) BETWEEN ? AND ?) new_customers,
        (SELECT COALESCE(SUM(amount),0) FROM payments WHERE payment_date BETWEEN ? AND ?) collection,
        (SELECT COALESCE(SUM(total),0) FROM invoices WHERE date(created_at) BETWEEN ? AND ?) billed""",
        (start,end,start,end,start,end,start,end,start,end)).fetchone()

    daily = db.execute("""WITH RECURSIVE days(d) AS (
        SELECT date(?) UNION ALL SELECT date(d,'+1 day') FROM days WHERE d < date(?)
    ) SELECT days.d date, COALESCE(p.collection,0) collection, COALESCE(b.bookings,0) bookings
      FROM days
      LEFT JOIN (SELECT payment_date d, SUM(amount) collection FROM payments WHERE payment_date BETWEEN ? AND ? GROUP BY payment_date) p ON p.d=days.d
      LEFT JOIN (SELECT date d, COUNT(*) bookings FROM bookings WHERE date BETWEEN ? AND ? GROUP BY date) b ON b.d=days.d
      ORDER BY days.d""", (start,end,start,end,start,end)).fetchall()

    job_status = db.execute("SELECT status, COUNT(*) count FROM job_cards GROUP BY status ORDER BY count DESC").fetchall()
    technicians = db.execute("""SELECT t.name, COUNT(j.id) jobs,
        COALESCE(SUM(CASE WHEN j.status='Closed' THEN 1 ELSE 0 END),0) closed
        FROM technicians t LEFT JOIN job_cards j ON j.technician_id=t.id
        GROUP BY t.id ORDER BY jobs DESC, t.name""").fetchall()
    services = db.execute("""SELECT COALESCE(s.name, ji.description) name,
        COUNT(ji.id) line_items, COALESCE(SUM(ji.quantity),0) quantity,
        COALESCE(SUM(ji.total),0) revenue
        FROM job_items ji LEFT JOIN services s ON s.id=ji.service_id
        GROUP BY COALESCE(s.name, ji.description) ORDER BY revenue DESC LIMIT 10""").fetchall()
    outstanding = db.execute("""SELECT i.invoice_no, i.total, i.paid_amount,
        (i.total-i.paid_amount) balance, c.name customer_name,
        v.registration, v.brand, v.model
        FROM invoices i JOIN job_cards j ON j.id=i.job_card_id
        JOIN customers c ON c.id=j.customer_id JOIN vehicles v ON v.id=j.vehicle_id
        WHERE i.total > i.paid_amount ORDER BY balance DESC""").fetchall()

    return render_template("reports.html", period=period, start=start, end=end,
                           summary=summary, daily=daily, job_status=job_status,
                           technicians=technicians, services=services, outstanding=outstanding)


@dashboard_bp.get("/admin/reports/export")
@login_required
@role_required("admin", "manager")
def reports_export():
    db = get_db()
    period, start, end = _date_range()
    rows = db.execute("""SELECT payment_date, payment_method, amount,
        transaction_id, i.invoice_no, c.name customer_name
        FROM payments p JOIN invoices i ON i.id=p.invoice_id
        LEFT JOIN job_cards j ON j.id=i.job_card_id
        LEFT JOIN customers c ON c.id=j.customer_id
        WHERE payment_date BETWEEN ? AND ? ORDER BY payment_date, p.id""", (start,end)).fetchall()
    import csv, io
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Payment Date", "Method", "Amount", "Transaction ID", "Invoice", "Customer"])
    writer.writerows([tuple(r) for r in rows])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=autocare_payments_{start}_to_{end}.csv"})
