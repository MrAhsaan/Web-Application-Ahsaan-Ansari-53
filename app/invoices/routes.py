import io
from datetime import datetime
from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table
from app.auth.utils import login_required, role_required
from app.database import get_db, now

invoices_bp = Blueprint("invoices", __name__)
ESTIMATE_STATUSES = ("Draft", "Sent", "Approved", "Rejected", "Expired")
ALLOWED_PAYMENT_METHODS = {"Cash", "UPI", "Card", "Bank Transfer", "Other"}


def money(value):
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def recalc_estimate(db, estimate_id):
    subtotal = round(db.execute("SELECT COALESCE(SUM(total),0) FROM estimate_items WHERE estimate_id=?", (estimate_id,)).fetchone()[0], 2)
    row = db.execute("SELECT discount,tax FROM estimates WHERE id=?", (estimate_id,)).fetchone()
    discount = min(money(row["discount"]), subtotal)
    tax = money(row["tax"])
    total = round(max(0, subtotal - discount + tax), 2)
    db.execute("UPDATE estimates SET subtotal=?,discount=?,tax=?,total=?,updated_at=? WHERE id=?", (subtotal,discount,tax,total,now(),estimate_id))
    return subtotal, discount, tax, total


@invoices_bp.get("/admin/billing")
@login_required
@role_required("admin", "manager", "receptionist")
def billing_home():
    db = get_db()
    estimates = db.execute("""SELECT e.*,c.name customer_name,v.registration,v.brand,v.model
        FROM estimates e JOIN customers c ON c.id=e.customer_id JOIN vehicles v ON v.id=e.vehicle_id
        ORDER BY e.id DESC""").fetchall()
    invoices = db.execute("""SELECT i.*,j.customer_id,c.name customer_name,v.registration,v.brand,v.model
        FROM invoices i JOIN job_cards j ON j.id=i.job_card_id JOIN customers c ON c.id=j.customer_id JOIN vehicles v ON v.id=j.vehicle_id
        ORDER BY i.id DESC""").fetchall()
    return render_template("billing.html", estimates=estimates, invoices=invoices)


@invoices_bp.post("/admin/estimate/create/<int:jid>")
@login_required
@role_required("admin", "manager", "receptionist")
def create_estimate(jid):
    db=get_db(); job=db.execute("SELECT * FROM job_cards WHERE id=?",(jid,)).fetchone()
    if not job: abort(404)
    existing=db.execute("SELECT id FROM estimates WHERE job_card_id=? AND status NOT IN ('Rejected','Expired') ORDER BY id DESC LIMIT 1",(jid,)).fetchone()
    if existing:
        flash("An active estimate already exists for this job card.","error")
        return redirect(url_for("invoices.estimate_view",eid=existing["id"]))
    ts=now(); no=f"EST-{datetime.now():%Y%m%d}-{jid:04d}"
    cur=db.execute("INSERT INTO estimates(customer_id,vehicle_id,job_card_id,estimate_no,created_at,updated_at) VALUES(?,?,?,?,?,?)",(job["customer_id"],job["vehicle_id"],jid,no,ts,ts))
    eid=cur.lastrowid
    items=db.execute("SELECT service_id,item_type,description,quantity,unit_price,total FROM job_items WHERE job_card_id=? ORDER BY id",(jid,)).fetchall()
    for x in items:
        db.execute("INSERT INTO estimate_items(estimate_id,service_id,item_type,description,quantity,unit_price,total,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",(eid,x["service_id"],x["item_type"],x["description"],x["quantity"],x["unit_price"],x["total"],ts,ts))
    recalc_estimate(db,eid); db.commit(); flash("Estimate created from Job Card.","success")
    return redirect(url_for("invoices.estimate_view",eid=eid))


@invoices_bp.route("/admin/estimate/<int:eid>",methods=["GET","POST"])
@login_required
@role_required("admin", "manager", "receptionist")
def estimate_view(eid):
    db=get_db(); e=db.execute("""SELECT e.*,c.name customer_name,c.phone,c.email,v.registration,v.brand,v.model,v.year,j.status job_status
        FROM estimates e JOIN customers c ON c.id=e.customer_id JOIN vehicles v ON v.id=e.vehicle_id LEFT JOIN job_cards j ON j.id=e.job_card_id WHERE e.id=?""",(eid,)).fetchone()
    if not e: abort(404)
    if request.method=="POST":
        status=request.form.get("status","Draft")
        if status not in ESTIMATE_STATUSES: abort(400)
        discount=money(request.form.get("discount")); tax=money(request.form.get("tax")); ts=now()
        try:
            db.execute("UPDATE estimates SET discount=?,tax=?,status=?,approved_at=?,updated_at=? WHERE id=?",(discount,tax,status,ts if status=="Approved" else None,ts,eid))
            types=request.form.getlist("item_type[]"); descs=request.form.getlist("item_description[]"); qtys=request.form.getlist("item_quantity[]"); prices=request.form.getlist("item_unit_price[]"); services=request.form.getlist("item_service_id[]")
            db.execute("DELETE FROM estimate_items WHERE estimate_id=?",(eid,))
            for i in range(max(len(types),len(descs),len(qtys),len(prices))):
                typ=types[i].strip().lower() if i<len(types) else "other"; desc=descs[i].strip() if i<len(descs) else ""
                if not desc or typ not in {"service","part","labor","other"}: continue
                q=money(qtys[i]) if i<len(qtys) else 1; price=money(prices[i]) if i<len(prices) else 0
                if q<=0: continue
                sid=None
                if i<len(services) and services[i]:
                    sid=int(services[i]) if services[i].isdigit() else None
                    if sid and not db.execute("SELECT id FROM services WHERE id=? AND is_active=1",(sid,)).fetchone(): sid=None
                db.execute("INSERT INTO estimate_items(estimate_id,service_id,item_type,description,quantity,unit_price,total,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",(eid,sid,typ,desc,q,price,round(q*price,2),ts,ts))
            recalc_estimate(db,eid); db.commit(); flash("Estimate updated.","success")
        except Exception:
            db.rollback(); flash("Could not update estimate.","error")
        return redirect(url_for("invoices.estimate_view",eid=eid))
    items=db.execute("SELECT ei.*,s.name service_name FROM estimate_items ei LEFT JOIN services s ON s.id=ei.service_id WHERE ei.estimate_id=? ORDER BY ei.id",(eid,)).fetchall()
    services=db.execute("SELECT * FROM services WHERE is_active=1 ORDER BY name").fetchall()
    invoice=db.execute("SELECT * FROM invoices WHERE estimate_id=? OR job_card_id=?",(eid,e["job_card_id"])).fetchone() if e["job_card_id"] else None
    return render_template("estimate_view.html",estimate=e,items=items,services=services,statuses=ESTIMATE_STATUSES,invoice=invoice)


@invoices_bp.post("/admin/estimate/<int:eid>/convert")
@login_required
@role_required("admin", "manager", "receptionist")
def convert_estimate(eid):
    db=get_db(); e=db.execute("SELECT * FROM estimates WHERE id=?",(eid,)).fetchone()
    if not e: abort(404)
    if e["status"]!="Approved":
        flash("Only an approved estimate can be converted to an invoice.","error"); return redirect(url_for("invoices.estimate_view",eid=eid))
    if not e["job_card_id"]:
        flash("This estimate is not linked to a job card.","error"); return redirect(url_for("invoices.estimate_view",eid=eid))
    existing=db.execute("SELECT id FROM invoices WHERE job_card_id=?",(e["job_card_id"],)).fetchone()
    if existing:
        flash("Invoice already exists for this job card.","error"); return redirect(url_for("jobs.job_view",jid=e["job_card_id"]))
    ts=now(); no=f"INV-{datetime.now():%Y%m%d}-{e['job_card_id']:04d}"
    db.execute("INSERT INTO invoices(job_card_id,estimate_id,invoice_no,subtotal,discount,tax,total,payment_status,paid_amount,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(e["job_card_id"],eid,no,e["subtotal"],e["discount"],e["tax"],e["total"],"Unpaid",0,ts,ts))
    db.commit(); flash("Approved estimate converted to invoice.","success")
    return redirect(url_for("jobs.job_view",jid=e["job_card_id"]))


@invoices_bp.post("/admin/invoice/<int:jid>")
@login_required
@role_required("admin", "manager", "receptionist")
def create_invoice(jid):
    db=get_db(); job=db.execute("SELECT * FROM job_cards WHERE id=?",(jid,)).fetchone()
    if not job: abort(404)
    if db.execute("SELECT id FROM invoices WHERE job_card_id=?",(jid,)).fetchone():
        flash("Invoice already exists for this job card.","error"); return redirect(url_for("jobs.job_view",jid=jid))
    subtotal=round(db.execute("SELECT COALESCE(SUM(total),0) FROM job_items WHERE job_card_id=?",(jid,)).fetchone()[0],2)
    discount=min(money(request.form.get("discount")),subtotal); tax=money(request.form.get("tax")); total=round(max(0,subtotal-discount+tax),2); ts=now(); no=f"INV-{datetime.now():%Y%m%d}-{jid:04d}"
    db.execute("INSERT INTO invoices(job_card_id,invoice_no,subtotal,discount,tax,total,payment_status,paid_amount,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(jid,no,subtotal,discount,tax,total,"Unpaid",0,ts,ts)); db.commit(); flash("Invoice created.","success"); return redirect(url_for("jobs.job_view",jid=jid))


@invoices_bp.post("/admin/invoice/<int:iid>/payment")
@login_required
@role_required("admin", "manager", "receptionist")
def payment(iid):
    db=get_db(); inv=db.execute("SELECT * FROM invoices WHERE id=?",(iid,)).fetchone()
    if not inv: abort(404)
    amount=money(request.form.get("paid_amount")); method=request.form.get("payment_method","").strip()
    if amount<=0 or method not in ALLOWED_PAYMENT_METHODS:
        flash("Enter a valid payment amount and payment method.","error"); return redirect(url_for("jobs.job_view",jid=inv["job_card_id"]))
    existing=money(db.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE invoice_id=?",(iid,)).fetchone()[0]); remaining=max(0,money(inv["total"])-existing)
    if amount>remaining:
        flash(f"Payment exceeds the remaining balance of ₹{remaining:.2f}.","error"); return redirect(url_for("jobs.job_view",jid=inv["job_card_id"]))
    ts=now(); db.execute("INSERT INTO payments(invoice_id,amount,payment_method,transaction_id,payment_date,notes,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",(iid,amount,method,request.form.get("transaction_id","").strip() or None,request.form.get("payment_date","").strip() or ts[:10],request.form.get("notes","").strip() or None,__import__('flask').session.get('user_id'),ts))
    paid=round(existing+amount,2); status="Paid" if paid>=money(inv["total"]) else "Partially Paid"; db.execute("UPDATE invoices SET paid_amount=?,payment_status=?,updated_at=? WHERE id=?",(paid,status,ts,iid)); db.commit(); flash("Payment recorded.","success"); return redirect(url_for("jobs.job_view",jid=inv["job_card_id"]))

# STEP 6: Payment & financial management additions
from datetime import date
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER


@invoices_bp.get("/admin/payments")
@login_required
@role_required("admin", "manager", "receptionist")
def payments_home():
    db = get_db()
    from_date = request.args.get("from", "").strip()
    to_date = request.args.get("to", "").strip()
    method = request.args.get("method", "").strip()
    params = []
    where = []
    if from_date:
        where.append("p.payment_date >= ?")
        params.append(from_date)
    if to_date:
        where.append("p.payment_date <= ?")
        params.append(to_date)
    if method in ALLOWED_PAYMENT_METHODS:
        where.append("p.payment_method = ?")
        params.append(method)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    payments = db.execute(f"""SELECT p.*, i.invoice_no, i.total invoice_total,
        c.name customer_name, c.phone, v.registration, v.brand, v.model,
        u.name created_by_name
        FROM payments p
        JOIN invoices i ON i.id=p.invoice_id
        JOIN job_cards j ON j.id=i.job_card_id
        JOIN customers c ON c.id=j.customer_id
        JOIN vehicles v ON v.id=j.vehicle_id
        LEFT JOIN users u ON u.id=p.created_by
        {clause} ORDER BY p.payment_date DESC, p.id DESC""", params).fetchall()

    total_collected = round(sum(float(p["amount"] or 0) for p in payments), 2)
    by_method = db.execute(f"""SELECT p.payment_method, COALESCE(SUM(p.amount),0) total
        FROM payments p {clause} GROUP BY p.payment_method ORDER BY total DESC""", params).fetchall()

    outstanding = db.execute("""SELECT i.id,i.invoice_no,i.total,i.paid_amount,
        ROUND(i.total-i.paid_amount,2) balance,i.payment_status,
        c.name customer_name,c.phone,v.registration,v.brand,v.model
        FROM invoices i JOIN job_cards j ON j.id=i.job_card_id
        JOIN customers c ON c.id=j.customer_id JOIN vehicles v ON v.id=j.vehicle_id
        WHERE i.total > i.paid_amount ORDER BY balance DESC,i.id DESC""").fetchall()
    outstanding_total = round(sum(float(x["balance"] or 0) for x in outstanding), 2)
    return render_template("payments.html", payments=payments, total_collected=total_collected,
                           by_method=by_method, outstanding=outstanding,
                           outstanding_total=outstanding_total, from_date=from_date,
                           to_date=to_date, method=method, methods=sorted(ALLOWED_PAYMENT_METHODS))


@invoices_bp.get("/admin/payment/<int:pid>/receipt")
@login_required
@role_required("admin", "manager", "receptionist")
def payment_receipt(pid):
    db = get_db()
    p = db.execute("""SELECT p.*,i.invoice_no,i.total invoice_total,i.paid_amount,
        c.name customer_name,c.phone,c.email,v.registration,v.brand,v.model
        FROM payments p JOIN invoices i ON i.id=p.invoice_id
        JOIN job_cards j ON j.id=i.job_card_id JOIN customers c ON c.id=j.customer_id
        JOIN vehicles v ON v.id=j.vehicle_id WHERE p.id=?""", (pid,)).fetchone()
    if not p:
        abort(404)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    styles["Title"].alignment = TA_CENTER
    balance = max(0, float(p["invoice_total"] or 0) - float(p["paid_amount"] or 0))
    story = [Paragraph("AUTOCARE GARAGE", styles["Title"]),
             Paragraph("PAYMENT RECEIPT", styles["Heading2"]), Spacer(1, 14)]
    rows = [["Receipt ID", f"PAY-{p['id']:06d}"], ["Payment Date", p["payment_date"]],
            ["Invoice", p["invoice_no"]], ["Customer", p["customer_name"]],
            ["Phone", p["phone"] or "N/A"],
            ["Vehicle", f"{p['brand'] or ''} {p['model'] or ''}".strip() or "N/A"],
            ["Registration", p["registration"] or "N/A"],
            ["Payment Method", p["payment_method"]], ["Amount Received", f"₹{float(p['amount']):.2f}"],
            ["Transaction ID", p["transaction_id"] or "N/A"],
            ["Invoice Total", f"₹{float(p['invoice_total']):.2f}"],
            ["Balance After Payment", f"₹{balance:.2f}"]]
    story.append(Table(rows, colWidths=[170, 320], style=[("GRID", (0,0), (-1,-1), .4, colors.grey),
        ("BACKGROUND", (0,0), (0,-1), colors.whitesmoke), ("PADDING", (0,0), (-1,-1), 7)]))
    if p["notes"]:
        story += [Spacer(1, 12), Paragraph(f"<b>Notes:</b> {p['notes']}", styles["Normal"])]
    story += [Spacer(1, 24), Paragraph("Thank you for choosing AutoCare Garage.", styles["Normal"])]
    doc.build(story)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"PAY-{p['id']:06d}.pdf", mimetype="application/pdf")


@invoices_bp.get("/admin/invoice/<int:iid>/pdf")
@login_required
@role_required("admin", "manager", "receptionist")
def invoice_pdf(iid):
    db=get_db(); inv=db.execute("SELECT * FROM invoices WHERE id=?",(iid,)).fetchone()
    if not inv: abort(404)
    job=db.execute("""SELECT j.*,c.name customer_name,c.phone,v.registration,v.brand,v.model FROM job_cards j JOIN customers c ON c.id=j.customer_id JOIN vehicles v ON v.id=j.vehicle_id WHERE j.id=?""",(inv["job_card_id"],)).fetchone()
    items=db.execute("SELECT * FROM job_items WHERE job_card_id=? ORDER BY id",(inv["job_card_id"],)).fetchall(); payments=db.execute("SELECT * FROM payments WHERE invoice_id=? ORDER BY payment_date,id",(iid,)).fetchall()
    buf=io.BytesIO(); doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=40,leftMargin=40,topMargin=40,bottomMargin=40); styles=getSampleStyleSheet(); styles["Title"].alignment=TA_CENTER
    story=[Paragraph("AUTOCARE GARAGE",styles["Title"]),Paragraph("Complete Car Care • Service • Denting • Painting • Washing",styles["Normal"]),Spacer(1,18),Paragraph(f"<b>Invoice:</b> {inv['invoice_no']} &nbsp;&nbsp; <b>Date:</b> {inv['created_at']}",styles["Normal"]),Spacer(1,10)]
    story.append(Table([["Customer",job["customer_name"]],["Phone",job["phone"]],["Vehicle",f"{job['brand'] or ''} {job['model']}"],["Registration",job["registration"] or "N/A"]],colWidths=[150,350],style=[("GRID",(0,0),(-1,-1),.4,colors.grey),("BACKGROUND",(0,0),(0,-1),colors.whitesmoke),("PADDING",(0,0),(-1,-1),7)])); story.append(Spacer(1,12))
    rows=[["Type","Description","Qty","Unit","Total"]]+[[i["item_type"].title(),i["description"],f"{i['quantity']:.2f}",f"₹{i['unit_price']:.2f}",f"₹{i['total']:.2f}"] for i in items]+[["","Subtotal","","",f"₹{inv['subtotal']:.2f}"],["","Discount","","",f"₹{inv['discount']:.2f}"],["","Tax","","",f"₹{inv['tax']:.2f}"],["","TOTAL","","",f"₹{inv['total']:.2f}"]]
    story.append(Table(rows,colWidths=[70,220,55,75,80],style=[("GRID",(0,0),(-1,-1),.4,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.whitesmoke),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTNAME",(1,-1),(-1,-1),"Helvetica-Bold"),("PADDING",(0,0),(-1,-1),6)])); story.append(Spacer(1,12)); story.append(Paragraph(f"<b>Payment status:</b> {inv['payment_status']} &nbsp;&nbsp; <b>Paid:</b> ₹{inv['paid_amount']:.2f} &nbsp;&nbsp; <b>Balance:</b> ₹{max(0,inv['total']-inv['paid_amount']):.2f}",styles["Normal"]))
    if payments: story += [Spacer(1,8),Paragraph("Payment history",styles["Heading3"]),Table([["Date","Method","Amount","Transaction"]]+[[p["payment_date"],p["payment_method"],f"₹{p['amount']:.2f}",p["transaction_id"] or "—"] for p in payments],colWidths=[100,110,90,195],style=[("GRID",(0,0),(-1,-1),.4,colors.grey),("PADDING",(0,0),(-1,-1),6)])]
    story += [Spacer(1,18),Paragraph("Thank you for choosing AutoCare Garage.",styles["Normal"])]
    doc.build(story); buf.seek(0); return send_file(buf,as_attachment=True,download_name=f"{inv['invoice_no']}.pdf",mimetype="application/pdf")
