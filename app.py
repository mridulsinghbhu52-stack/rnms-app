# -*- coding: utf-8 -*-
"""
RNMS — नगर पंचायत रतसर कलां वित्त एवं निर्माण कार्य प्रबंधन पोर्टल
Core MVP: Login/Roles -> मद/GO/आय -> कार्य/टेंडर/वर्क ऑर्डर -> बिल/भुगतान अनुमोदन -> कैशबुक
"""
import os
from datetime import datetime, date

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

import db
from utils import login_required, require_role, to_float, fmt_amount

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "rnms-dev-secret-change-in-production")
app.jinja_env.filters["amt"] = fmt_amount


def today():
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = db.get_db()
        user = db.fetchone(
            conn,
            """SELECT u.*, r.role_code, r.role_name FROM users u
               JOIN roles r ON r.role_id = u.role_id
               WHERE u.username = ? AND u.status = 'ACTIVE'""",
            (username,),
        )
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["user_id"]
            session["username"] = user["username"]
            session["full_name"] = user["full_name"]
            session["role_code"] = user["role_code"]
            session["role_name"] = user["role_name"]
            flash(f"स्वागत है, {user['full_name']}", "success")
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("गलत उपयोगकर्ता नाम या पासवर्ड।", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def dashboard():
    conn = db.get_db()
    schemes = db.fetchall(conn, "SELECT * FROM schemes WHERE is_active = 1 OR is_active = TRUE ORDER BY scheme_name")
    summary = []
    for s in schemes:
        opening = db.fetchone(conn, "SELECT COALESCE(SUM(amount),0) AS v FROM opening_balances WHERE scheme_id=?", (s["scheme_id"],))["v"]
        installments = db.fetchone(conn, "SELECT COALESCE(SUM(amount_received),0) AS v FROM installments WHERE scheme_id=?", (s["scheme_id"],))["v"]
        interest = db.fetchone(conn, "SELECT COALESCE(SUM(amount),0) AS v FROM bank_interest WHERE scheme_id=? AND (is_usable=1 OR is_usable=TRUE)", (s["scheme_id"],))["v"]
        expenditure = db.fetchone(conn, """SELECT COALESCE(SUM(p.net_payment),0) AS v FROM payments p
                                            JOIN works w ON w.work_id = p.work_id
                                            WHERE w.scheme_id=? AND p.status='POSTED'""", (s["scheme_id"],))["v"]
        charges = db.fetchone(conn, "SELECT COALESCE(SUM(amount),0) AS v FROM bank_charges WHERE scheme_id=? AND txn_type='CHARGE'", (s["scheme_id"],))["v"]
        refunds = db.fetchone(conn, "SELECT COALESCE(SUM(amount),0) AS v FROM bank_charges WHERE scheme_id=? AND txn_type='REFUND'", (s["scheme_id"],))["v"]
        available = float(opening) + float(installments) + float(interest) - float(expenditure) - float(charges) + float(refunds)
        summary.append({
            "scheme": s, "opening": opening, "installments": installments, "interest": interest,
            "expenditure": expenditure, "charges": charges, "refunds": refunds, "available": available,
        })
    pending_counts = {}
    if session["role_code"] in ("ACCOUNTANT", "EO_ADMIN", "ADMIN"):
        pending_counts["verify"] = db.fetchone(conn, "SELECT COUNT(*) AS c FROM payments WHERE status='ENTERED'")["c"]
        pending_counts["approve"] = db.fetchone(conn, "SELECT COUNT(*) AS c FROM payments WHERE status='VERIFIED'")["c"]
        pending_counts["post"] = db.fetchone(conn, "SELECT COUNT(*) AS c FROM payments WHERE status='APPROVED'")["c"]
    works_count = db.fetchone(conn, "SELECT COUNT(*) AS c FROM works")["c"]
    conn.close()
    return render_template("dashboard.html", summary=summary, pending_counts=pending_counts, works_count=works_count)


# ---------------------------------------------------------------------------
# Masters (ADMIN)
# ---------------------------------------------------------------------------

@app.route("/masters", methods=["GET"])
@login_required
def masters():
    conn = db.get_db()
    data = {
        "schemes": db.fetchall(conn, "SELECT * FROM schemes ORDER BY scheme_id DESC"),
        "wards": db.fetchall(conn, "SELECT * FROM wards ORDER BY ward_id DESC"),
        "fys": db.fetchall(conn, "SELECT * FROM financial_years ORDER BY fy_id DESC"),
        "asset_types": db.fetchall(conn, "SELECT * FROM asset_types ORDER BY asset_type_id DESC"),
        "firms": db.fetchall(conn, "SELECT * FROM firms ORDER BY firm_id DESC"),
        "bank_accounts": db.fetchall(conn, """SELECT b.*, s.scheme_name FROM bank_accounts b
                                               LEFT JOIN schemes s ON s.scheme_id=b.scheme_id ORDER BY b.account_id DESC"""),
    }
    conn.close()
    return render_template("masters.html", **data)


@app.route("/masters/schemes/new", methods=["POST"])
@require_role("ADMIN")
def new_scheme():
    conn = db.get_db()
    db.insert_and_get_id(conn, "schemes", "scheme_id",
        ["scheme_code", "scheme_name", "scheme_category", "interest_usable", "non_tender_allowed", "is_active"],
        (request.form["scheme_code"], request.form["scheme_name"], request.form["scheme_category"],
         1 if request.form.get("interest_usable") else 0,
         1 if request.form.get("non_tender_allowed") else 0, 1))
    conn.close()
    flash("मद जोड़ी गई।", "success")
    return redirect(url_for("masters"))


@app.route("/masters/wards/new", methods=["POST"])
@require_role("ADMIN")
def new_ward():
    conn = db.get_db()
    db.insert_and_get_id(conn, "wards", "ward_id", ["ward_no", "ward_name"],
                          (request.form["ward_no"], request.form["ward_name"]))
    conn.close()
    flash("वार्ड जोड़ा गया।", "success")
    return redirect(url_for("masters"))


@app.route("/masters/fy/new", methods=["POST"])
@require_role("ADMIN")
def new_fy():
    conn = db.get_db()
    db.insert_and_get_id(conn, "financial_years", "fy_id",
                          ["fy_name", "start_date", "end_date", "is_current"],
                          (request.form["fy_name"], request.form["start_date"], request.form["end_date"],
                           1 if request.form.get("is_current") else 0))
    conn.close()
    flash("वित्तीय वर्ष जोड़ा गया।", "success")
    return redirect(url_for("masters"))


@app.route("/masters/asset-types/new", methods=["POST"])
@require_role("ADMIN")
def new_asset_type():
    conn = db.get_db()
    db.insert_and_get_id(conn, "asset_types", "asset_type_id", ["asset_type_name"], (request.form["asset_type_name"],))
    conn.close()
    flash("परिसंपत्ति प्रकार जोड़ा गया।", "success")
    return redirect(url_for("masters"))


@app.route("/masters/firms/new", methods=["POST"])
@require_role("ADMIN", "ACCOUNT_OPERATOR")
def new_firm():
    conn = db.get_db()
    db.insert_and_get_id(conn, "firms", "firm_id",
        ["firm_name", "proprietor_name", "gst_no", "pan_no", "contact_no", "email", "status"],
        (request.form["firm_name"], request.form.get("proprietor_name"), request.form.get("gst_no"),
         request.form.get("pan_no"), request.form.get("contact_no"), request.form.get("email"), "ACTIVE"))
    conn.close()
    flash("फर्म जोड़ी गई।", "success")
    return redirect(url_for("masters"))


@app.route("/masters/bank-accounts/new", methods=["POST"])
@require_role("ADMIN")
def new_bank_account():
    conn = db.get_db()
    scheme_id = request.form.get("scheme_id") or None
    db.insert_and_get_id(conn, "bank_accounts", "account_id",
        ["account_no", "bank_name", "branch_name", "ifsc_code", "scheme_id", "opening_date", "is_active"],
        (request.form["account_no"], request.form["bank_name"], request.form.get("branch_name"),
         request.form.get("ifsc_code"), scheme_id, request.form.get("opening_date") or None, 1))
    conn.close()
    flash("बैंक खाता जोड़ा गया।", "success")
    return redirect(url_for("masters"))


# ---------------------------------------------------------------------------
# Cashbook helper
# ---------------------------------------------------------------------------

def post_cashbook_entry(conn, bank_account_id, scheme_id, entry_date, particulars,
                         receipt=0, payment=0, reference_type=None, reference_id=None, created_by=None):
    last = db.fetchone(conn, """SELECT running_balance FROM cashbook_entries
                                 WHERE bank_account_id=? ORDER BY entry_id DESC LIMIT 1""", (bank_account_id,))
    last_balance = float(last["running_balance"]) if last else 0.0
    new_balance = last_balance + float(receipt) - float(payment)
    db.insert_and_get_id(conn, "cashbook_entries", "entry_id",
        ["bank_account_id", "scheme_id", "entry_date", "particulars", "receipt_amount",
         "payment_amount", "running_balance", "reference_type", "reference_id", "created_by"],
        (bank_account_id, scheme_id, entry_date, particulars, receipt, payment,
         new_balance, reference_type, reference_id, created_by))
    return new_balance


def primary_bank_account(conn, scheme_id):
    row = db.fetchone(conn, """SELECT account_id FROM bank_accounts
                                WHERE scheme_id=? AND (is_active=1 OR is_active=TRUE)
                                ORDER BY account_id LIMIT 1""", (scheme_id,))
    return row["account_id"] if row else None


# ---------------------------------------------------------------------------
# Finance / Income
# ---------------------------------------------------------------------------

@app.route("/finance")
@login_required
def finance():
    conn = db.get_db()
    data = {
        "schemes": db.fetchall(conn, "SELECT * FROM schemes WHERE is_active=1 OR is_active=TRUE ORDER BY scheme_name"),
        "fys": db.fetchall(conn, "SELECT * FROM financial_years ORDER BY fy_id DESC"),
        "bank_accounts": db.fetchall(conn, "SELECT * FROM bank_accounts ORDER BY account_id DESC"),
        "opening_balances": db.fetchall(conn, """SELECT ob.*, s.scheme_name, f.fy_name FROM opening_balances ob
                                                   JOIN schemes s ON s.scheme_id=ob.scheme_id
                                                   JOIN financial_years f ON f.fy_id=ob.fy_id
                                                   ORDER BY ob.opening_balance_id DESC"""),
        "gos": db.fetchall(conn, """SELECT g.*, s.scheme_name,
                                     (SELECT COALESCE(SUM(amount_received),0) FROM installments WHERE go_id=g.go_id) AS received
                                     FROM go_register g JOIN schemes s ON s.scheme_id=g.scheme_id
                                     ORDER BY g.go_id DESC"""),
        "interest": db.fetchall(conn, """SELECT bi.*, s.scheme_name, ba.account_no FROM bank_interest bi
                                          JOIN schemes s ON s.scheme_id=bi.scheme_id
                                          JOIN bank_accounts ba ON ba.account_id=bi.bank_account_id
                                          ORDER BY bi.interest_id DESC"""),
        "charges": db.fetchall(conn, """SELECT bc.*, s.scheme_name, ba.account_no FROM bank_charges bc
                                         JOIN schemes s ON s.scheme_id=bc.scheme_id
                                         JOIN bank_accounts ba ON ba.account_id=bc.bank_account_id
                                         ORDER BY bc.charge_id DESC"""),
    }
    conn.close()
    return render_template("finance.html", **data)


@app.route("/finance/opening-balance/new", methods=["POST"])
@require_role("ACCOUNT_OPERATOR", "ADMIN")
def new_opening_balance():
    conn = db.get_db()
    scheme_id = int(request.form["scheme_id"])
    fy_id = int(request.form["fy_id"])
    amount = to_float(request.form["amount"])
    db.insert_and_get_id(conn, "opening_balances", "opening_balance_id",
        ["scheme_id", "fy_id", "amount", "remarks", "created_by"],
        (scheme_id, fy_id, amount, request.form.get("remarks"), session["user_id"]))
    bank_account_id = int(request.form["bank_account_id"]) if request.form.get("bank_account_id") else primary_bank_account(conn, scheme_id)
    if bank_account_id and amount:
        post_cashbook_entry(conn, bank_account_id, scheme_id, today(), "आरम्भिक अवशेष / Opening Balance",
                             receipt=amount, reference_type="OPENING", created_by=session["user_id"])
    conn.commit()
    conn.close()
    flash("आरम्भिक अवशेष दर्ज हुआ।", "success")
    return redirect(url_for("finance"))


@app.route("/finance/go/new", methods=["POST"])
@require_role("ACCOUNT_OPERATOR", "ADMIN")
def new_go():
    conn = db.get_db()
    db.insert_and_get_id(conn, "go_register", "go_id",
        ["scheme_id", "fy_id", "go_number", "go_date", "subject", "total_sanctioned_amount", "remarks", "created_by"],
        (int(request.form["scheme_id"]), request.form.get("fy_id") or None, request.form["go_number"],
         request.form["go_date"], request.form.get("subject"), to_float(request.form["total_sanctioned_amount"]),
         request.form.get("remarks"), session["user_id"]))
    conn.close()
    flash("GO दर्ज हुआ।", "success")
    return redirect(url_for("finance"))


@app.route("/finance/go/<int:go_id>/installments/new", methods=["POST"])
@require_role("ACCOUNT_OPERATOR", "ADMIN")
def new_installment(go_id):
    conn = db.get_db()
    go = db.fetchone(conn, "SELECT * FROM go_register WHERE go_id=?", (go_id,))
    if not go:
        conn.close()
        flash("GO नहीं मिला।", "error")
        return redirect(url_for("finance"))
    count = db.fetchone(conn, "SELECT COUNT(*) AS c FROM installments WHERE go_id=?", (go_id,))["c"]
    amount = to_float(request.form["amount_received"])
    bank_account_id = int(request.form["bank_account_id"])
    db.insert_and_get_id(conn, "installments", "installment_id",
        ["go_id", "scheme_id", "installment_no", "amount_received", "received_date",
         "bank_account_id", "bank_reference_no", "remarks", "created_by"],
        (go_id, go["scheme_id"], count + 1, amount, request.form["received_date"], bank_account_id,
         request.form.get("bank_reference_no"), request.form.get("remarks"), session["user_id"]))
    post_cashbook_entry(conn, bank_account_id, go["scheme_id"], request.form["received_date"],
                         f"किस्त प्राप्त — GO {go['go_number']} (किस्त {count + 1})",
                         receipt=amount, reference_type="INSTALLMENT", reference_id=go_id, created_by=session["user_id"])
    conn.commit()
    conn.close()
    flash("किस्त दर्ज हुई।", "success")
    return redirect(url_for("finance"))


@app.route("/finance/interest/new", methods=["POST"])
@require_role("ACCOUNT_OPERATOR", "ADMIN")
def new_interest():
    conn = db.get_db()
    scheme_id = int(request.form["scheme_id"])
    bank_account_id = int(request.form["bank_account_id"])
    amount = to_float(request.form["amount"])
    scheme = db.fetchone(conn, "SELECT interest_usable FROM schemes WHERE scheme_id=?", (scheme_id,))
    is_usable = 1 if scheme and (scheme["interest_usable"] in (1, True)) else 0
    db.insert_and_get_id(conn, "bank_interest", "interest_id",
        ["bank_account_id", "scheme_id", "amount", "credit_date", "is_usable", "remarks", "created_by"],
        (bank_account_id, scheme_id, amount, request.form["credit_date"], is_usable,
         request.form.get("remarks"), session["user_id"]))
    post_cashbook_entry(conn, bank_account_id, scheme_id, request.form["credit_date"], "बैंक ब्याज / Bank Interest",
                         receipt=amount, reference_type="INTEREST", created_by=session["user_id"])
    conn.commit()
    conn.close()
    flash("बैंक ब्याज दर्ज हुआ।" + ("" if is_usable else " (यह मद ब्याज व्यय हेतु उपयोग योग्य नहीं है)"), "success")
    return redirect(url_for("finance"))


@app.route("/finance/charges/new", methods=["POST"])
@require_role("ACCOUNT_OPERATOR", "ADMIN")
def new_charge():
    conn = db.get_db()
    scheme_id = int(request.form["scheme_id"])
    bank_account_id = int(request.form["bank_account_id"])
    amount = to_float(request.form["amount"])
    txn_type = request.form["txn_type"]
    db.insert_and_get_id(conn, "bank_charges", "charge_id",
        ["bank_account_id", "scheme_id", "txn_type", "amount", "txn_date", "remarks", "created_by"],
        (bank_account_id, scheme_id, txn_type, amount, request.form["txn_date"],
         request.form.get("remarks"), session["user_id"]))
    if txn_type == "CHARGE":
        post_cashbook_entry(conn, bank_account_id, scheme_id, request.form["txn_date"], "बैंक चार्ज / Bank Charge",
                             payment=amount, reference_type="BANK_CHARGE", created_by=session["user_id"])
    else:
        post_cashbook_entry(conn, bank_account_id, scheme_id, request.form["txn_date"], "बैंक चार्ज वापसी / Refund",
                             receipt=amount, reference_type="REFUND", created_by=session["user_id"])
    conn.commit()
    conn.close()
    flash("प्रविष्टि दर्ज हुई।", "success")
    return redirect(url_for("finance"))


# ---------------------------------------------------------------------------
# Works / Tenders / Work Orders
# ---------------------------------------------------------------------------

@app.route("/works")
@login_required
def works_list():
    conn = db.get_db()
    works = db.fetchall(conn, """SELECT w.*, s.scheme_name, wd.ward_name FROM works w
                                  JOIN schemes s ON s.scheme_id=w.scheme_id
                                  LEFT JOIN wards wd ON wd.ward_id=w.ward_id
                                  ORDER BY w.work_id DESC""")
    schemes = db.fetchall(conn, "SELECT * FROM schemes WHERE is_active=1 OR is_active=TRUE ORDER BY scheme_name")
    wards = db.fetchall(conn, "SELECT * FROM wards ORDER BY ward_no")
    fys = db.fetchall(conn, "SELECT * FROM financial_years ORDER BY fy_id DESC")
    asset_types = db.fetchall(conn, "SELECT * FROM asset_types ORDER BY asset_type_name")
    conn.close()
    return render_template("works_list.html", works=works, schemes=schemes, wards=wards, fys=fys, asset_types=asset_types)


@app.route("/works/new", methods=["POST"])
@require_role("ACCOUNT_OPERATOR", "ADMIN")
def new_work():
    conn = db.get_db()
    scheme_id = int(request.form["scheme_id"])
    fy_id = int(request.form["fy_id"])
    scheme = db.fetchone(conn, "SELECT scheme_code, non_tender_allowed FROM schemes WHERE scheme_id=?", (scheme_id,))
    fy = db.fetchone(conn, "SELECT fy_name FROM financial_years WHERE fy_id=?", (fy_id,))
    count = db.fetchone(conn, "SELECT COUNT(*) AS c FROM works WHERE scheme_id=? AND fy_id=?", (scheme_id, fy_id))["c"]
    work_code = f"RNMS/{scheme['scheme_code']}/{fy['fy_name']}/{count + 1:04d}"
    is_tendered = 1 if request.form.get("is_tendered") else 0
    if not is_tendered and not scheme["non_tender_allowed"]:
        conn.close()
        flash("इस मद में बिना टेंडर कार्य दर्ज करने की अनुमति नहीं है।", "error")
        return redirect(url_for("works_list"))
    db.insert_and_get_id(conn, "works", "work_id",
        ["work_code", "scheme_id", "ward_id", "fy_id", "asset_type_id", "work_name", "work_source",
         "is_tendered", "estimated_amount", "status", "proposed_date", "created_by"],
        (work_code, scheme_id, request.form.get("ward_id") or None, fy_id, request.form.get("asset_type_id") or None,
         request.form["work_name"], request.form.get("work_source", "NEW"), is_tendered,
         to_float(request.form["estimated_amount"]), "PROPOSED", today(), session["user_id"]))
    conn.close()
    flash(f"कार्य दर्ज हुआ — {work_code}", "success")
    return redirect(url_for("works_list"))


@app.route("/works/<int:work_id>")
@login_required
def work_detail(work_id):
    conn = db.get_db()
    work = db.fetchone(conn, """SELECT w.*, s.scheme_name, s.scheme_id FROM works w
                                 JOIN schemes s ON s.scheme_id=w.scheme_id WHERE w.work_id=?""", (work_id,))
    if not work:
        conn.close()
        flash("कार्य नहीं मिला।", "error")
        return redirect(url_for("works_list"))
    tenders = db.fetchall(conn, "SELECT * FROM tenders WHERE work_id=? ORDER BY tender_id DESC", (work_id,))
    firms = db.fetchall(conn, "SELECT * FROM firms WHERE status='ACTIVE' ORDER BY firm_name")
    work_orders = db.fetchall(conn, """SELECT wo.*, f.firm_name FROM work_orders wo
                                        JOIN firms f ON f.firm_id=wo.firm_id WHERE wo.work_id=? ORDER BY wo.wo_id DESC""", (work_id,))
    bills = db.fetchall(conn, """SELECT b.*, f.firm_name FROM bills b JOIN firms f ON f.firm_id=b.firm_id
                                  WHERE b.work_id=? ORDER BY b.bill_sequence_no""", (work_id,))
    payments = db.fetchall(conn, """SELECT p.*, b.bill_no FROM payments p JOIN bills b ON b.bill_id=p.bill_id
                                     WHERE p.work_id=? ORDER BY p.payment_id DESC""", (work_id,))
    total_paid = db.fetchone(conn, "SELECT COALESCE(SUM(net_payment),0) AS v FROM payments WHERE work_id=? AND status='POSTED'", (work_id,))["v"]
    latest_tender = tenders[0] if tenders else None
    conn.close()
    return render_template("work_detail.html", work=work, tenders=tenders, firms=firms, work_orders=work_orders,
                            bills=bills, payments=payments, total_paid=total_paid, latest_tender=latest_tender)


@app.route("/works/<int:work_id>/tenders/new", methods=["POST"])
@require_role("ACCOUNT_OPERATOR", "ADMIN")
def new_tender(work_id):
    conn = db.get_db()
    db.insert_and_get_id(conn, "tenders", "tender_id",
        ["work_id", "tender_no", "tender_date", "tender_amount", "l1_firm_id", "l1_amount", "status", "created_by"],
        (work_id, request.form["tender_no"], request.form["tender_date"], to_float(request.form["tender_amount"]),
         request.form.get("l1_firm_id") or None, to_float(request.form.get("l1_amount")) or None, "AWARDED", session["user_id"]))
    db.run(conn, "UPDATE works SET status='TENDERED' WHERE work_id=?", (work_id,))
    conn.commit()
    conn.close()
    flash("टेंडर दर्ज हुआ।", "success")
    return redirect(url_for("work_detail", work_id=work_id))


@app.route("/works/<int:work_id>/work-orders/new", methods=["POST"])
@require_role("ACCOUNT_OPERATOR", "ADMIN")
def new_work_order(work_id):
    conn = db.get_db()
    db.insert_and_get_id(conn, "work_orders", "wo_id",
        ["work_id", "tender_id", "firm_id", "wo_number", "wo_date", "wo_amount", "created_by"],
        (work_id, request.form.get("tender_id") or None, int(request.form["firm_id"]), request.form["wo_number"],
         request.form["wo_date"], to_float(request.form["wo_amount"]), session["user_id"]))
    db.run(conn, "UPDATE works SET status='WORK_ORDER_ISSUED' WHERE work_id=?", (work_id,))
    conn.commit()
    conn.close()
    flash("Work Order दर्ज हुआ।", "success")
    return redirect(url_for("work_detail", work_id=work_id))


@app.route("/works/<int:work_id>/bills/new", methods=["POST"])
@require_role("ACCOUNT_OPERATOR", "ADMIN")
def new_bill(work_id):
    conn = db.get_db()
    count = db.fetchone(conn, "SELECT COUNT(*) AS c FROM bills WHERE work_id=?", (work_id,))["c"]
    amount_excl = to_float(request.form["amount_excl_gst"])
    gst_rate = to_float(request.form["gst_rate"])
    gst_amount = round(amount_excl * gst_rate / 100.0, 2)
    amount_incl = round(amount_excl + gst_amount, 2)
    db.insert_and_get_id(conn, "bills", "bill_id",
        ["work_id", "firm_id", "bill_no", "bill_date", "bill_sequence_no", "amount_excl_gst",
         "gst_rate", "gst_amount", "amount_incl_gst", "status", "created_by"],
        (work_id, int(request.form["firm_id"]), request.form["bill_no"], request.form["bill_date"], count + 1,
         amount_excl, gst_rate, gst_amount, amount_incl, "SUBMITTED", session["user_id"]))
    db.run(conn, "UPDATE works SET status='IN_PROGRESS' WHERE work_id=? AND status NOT IN ('COMPLETED','CLOSED')", (work_id,))
    conn.commit()
    conn.close()
    flash(f"बिल #{count + 1} दर्ज हुआ — कुल (GST सहित) {fmt_amount(amount_incl)}", "success")
    return redirect(url_for("work_detail", work_id=work_id))


# ---------------------------------------------------------------------------
# Payments — Account Operator Entry -> Accountant Verify -> EO Approve -> Post
# ---------------------------------------------------------------------------

@app.route("/bills/<int:bill_id>/payments/new", methods=["POST"])
@require_role("ACCOUNT_OPERATOR", "ADMIN")
def new_payment(bill_id):
    conn = db.get_db()
    bill = db.fetchone(conn, "SELECT * FROM bills WHERE bill_id=?", (bill_id,))
    work = db.fetchone(conn, "SELECT * FROM works WHERE work_id=?", (bill["work_id"],))
    latest_tender = db.fetchone(conn, "SELECT * FROM tenders WHERE work_id=? ORDER BY tender_id DESC LIMIT 1", (work["work_id"],))
    gross = float(bill["amount_incl_gst"])
    no_deduction = bool(request.form.get("no_deduction"))
    include_cess = bool(request.form.get("include_labour_cess"))
    if no_deduction:
        cgst = sgst = income_tax = labour_cess = 0.0
    else:
        cgst = round(gross * 0.01, 2)
        sgst = round(gross * 0.01, 2)
        income_tax = round(gross * 0.02, 2)
        labour_cess = round(gross * 0.01, 2) if include_cess else 0.0
    total_deduction = round(cgst + sgst + income_tax + labour_cess, 2)
    net_payment = round(gross - total_deduction, 2)
    prior_posted = db.fetchone(conn, "SELECT COALESCE(SUM(net_payment),0) AS v FROM payments WHERE work_id=? AND status='POSTED'", (work["work_id"],))["v"]
    balance_sanction = round(float(work["estimated_amount"]) - float(prior_posted) - net_payment, 2)
    balance_l1 = round(float(latest_tender["l1_amount"]) - float(prior_posted) - net_payment, 2) if latest_tender and latest_tender["l1_amount"] else None
    payment_id = db.insert_and_get_id(conn, "payments", "payment_id",
        ["bill_id", "work_id", "gross_amount", "cgst_1pct", "sgst_1pct", "income_tax_2pct", "labour_cess_1pct",
         "no_deduction", "total_deduction", "net_payment", "balance_against_sanction", "balance_against_l1",
         "ppa_no", "ppa_date", "status", "entered_by", "remarks"],
        (bill_id, work["work_id"], gross, cgst, sgst, income_tax, labour_cess, 1 if no_deduction else 0,
         total_deduction, net_payment, balance_sanction, balance_l1, request.form.get("ppa_no"),
         request.form.get("ppa_date") or None, "ENTERED", session["user_id"], request.form.get("remarks")))
    db.insert_and_get_id(conn, "payment_approval_log", "log_id",
        ["payment_id", "action", "actor_user_id", "remarks"],
        (payment_id, "ENTRY", session["user_id"], "Account Operator entry"))
    db.run(conn, "UPDATE bills SET status='APPROVED' WHERE bill_id=?", (bill_id,))
    conn.commit()
    conn.close()
    flash(f"भुगतान दर्ज हुआ — नेट राशि {fmt_amount(net_payment)} (सत्यापन हेतु लंबित)", "success")
    return redirect(url_for("work_detail", work_id=work["work_id"]))


@app.route("/payments")
@login_required
def payments_queue():
    conn = db.get_db()
    q_map = {
        "ENTERED": "सत्यापन हेतु लंबित (Accountant)",
        "VERIFIED": "अनुमोदन हेतु लंबित (EO)",
        "APPROVED": "Posting हेतु लंबित (Accountant)",
    }
    rows = db.fetchall(conn, """SELECT p.*, w.work_code, w.work_name, b.bill_no FROM payments p
                                 JOIN works w ON w.work_id=p.work_id JOIN bills b ON b.bill_id=p.bill_id
                                 ORDER BY p.payment_id DESC""")
    conn.close()
    return render_template("payments_queue.html", rows=rows, q_map=q_map)


@app.route("/payments/<int:payment_id>/verify", methods=["POST"])
@require_role("ACCOUNTANT", "ADMIN")
def verify_payment(payment_id):
    conn = db.get_db()
    db.run(conn, "UPDATE payments SET status='VERIFIED', verified_by=?, verified_at=? WHERE payment_id=? AND status='ENTERED'",
           (session["user_id"], datetime.now().isoformat(), payment_id))
    db.insert_and_get_id(conn, "payment_approval_log", "log_id",
        ["payment_id", "action", "actor_user_id", "remarks"], (payment_id, "VERIFY", session["user_id"], request.form.get("remarks")))
    conn.commit()
    conn.close()
    flash("भुगतान सत्यापित हुआ।", "success")
    return redirect(url_for("payments_queue"))


@app.route("/payments/<int:payment_id>/approve", methods=["POST"])
@require_role("EO_ADMIN", "ADMIN")
def approve_payment(payment_id):
    conn = db.get_db()
    db.run(conn, "UPDATE payments SET status='APPROVED', approved_by=?, approved_at=? WHERE payment_id=? AND status='VERIFIED'",
           (session["user_id"], datetime.now().isoformat(), payment_id))
    db.insert_and_get_id(conn, "payment_approval_log", "log_id",
        ["payment_id", "action", "actor_user_id", "remarks"], (payment_id, "APPROVE", session["user_id"], request.form.get("remarks")))
    conn.commit()
    conn.close()
    flash("भुगतान स्वीकृत हुआ (EO Approval)।", "success")
    return redirect(url_for("payments_queue"))


@app.route("/payments/<int:payment_id>/post", methods=["POST"])
@require_role("ACCOUNTANT", "ADMIN")
def post_payment(payment_id):
    conn = db.get_db()
    payment = db.fetchone(conn, "SELECT * FROM payments WHERE payment_id=? AND status='APPROVED'", (payment_id,))
    if not payment:
        conn.close()
        flash("यह भुगतान Posting योग्य स्थिति में नहीं है।", "error")
        return redirect(url_for("payments_queue"))
    work = db.fetchone(conn, "SELECT * FROM works WHERE work_id=?", (payment["work_id"],))
    bill = db.fetchone(conn, "SELECT * FROM bills WHERE bill_id=?", (payment["bill_id"],))
    bank_account_id = primary_bank_account(conn, work["scheme_id"])
    if not bank_account_id:
        conn.close()
        flash("इस मद हेतु कोई बैंक खाता सेट नहीं है — पहले Masters में बैंक खाता जोड़ें।", "error")
        return redirect(url_for("payments_queue"))
    db.run(conn, "UPDATE payments SET status='POSTED', posted_by=?, posted_at=? WHERE payment_id=?",
           (session["user_id"], datetime.now().isoformat(), payment_id))
    db.insert_and_get_id(conn, "payment_approval_log", "log_id",
        ["payment_id", "action", "actor_user_id", "remarks"], (payment_id, "POST", session["user_id"], request.form.get("remarks")))
    post_cashbook_entry(conn, bank_account_id, work["scheme_id"], today(),
                         f"भुगतान — {work['work_code']} / बिल {bill['bill_no']}",
                         payment=float(payment["net_payment"]), reference_type="PAYMENT",
                         reference_id=payment_id, created_by=session["user_id"])
    db.run(conn, "UPDATE bills SET status='PAID' WHERE bill_id=?", (payment["bill_id"],))
    conn.commit()
    conn.close()
    flash("भुगतान Post हुआ एवं कैशबुक में दर्ज हुआ।", "success")
    return redirect(url_for("payments_queue"))


# ---------------------------------------------------------------------------
# Cashbook
# ---------------------------------------------------------------------------

@app.route("/cashbook")
@login_required
def cashbook():
    conn = db.get_db()
    scheme_id = request.args.get("scheme_id")
    sql = """SELECT c.*, s.scheme_name, ba.account_no FROM cashbook_entries c
             JOIN schemes s ON s.scheme_id=c.scheme_id
             JOIN bank_accounts ba ON ba.account_id=c.bank_account_id"""
    params = ()
    if scheme_id:
        sql += " WHERE c.scheme_id=?"
        params = (scheme_id,)
    sql += " ORDER BY c.entry_id DESC"
    entries = db.fetchall(conn, sql, params)
    schemes = db.fetchall(conn, "SELECT * FROM schemes ORDER BY scheme_name")
    conn.close()
    return render_template("cashbook.html", entries=entries, schemes=schemes, selected_scheme=scheme_id)


# ---------------------------------------------------------------------------
# Bootstrap: first-run schema + seed
# ---------------------------------------------------------------------------

def bootstrap():
    conn = db.get_db()
    db.init_schema(conn)
    existing = db.fetchone(conn, "SELECT COUNT(*) AS c FROM roles")["c"]
    if not existing:
        role_rows = [
            ("EO_ADMIN", "EO / Admin", "अंतिम स्वीकृति, लॉक, सभी रिपोर्ट एवं नियंत्रण"),
            ("ACCOUNTANT", "Accountant", "वित्तीय जाँच, भुगतान सत्यापन, माह बन्द करना"),
            ("ACCOUNT_OPERATOR", "Account Operator", "आय, कार्य, टेंडर, बिल एवं भुगतान की डेटा एंट्री"),
            ("ADMIN", "Admin", "मास्टर डेटा, उपयोगकर्ता एवं सिस्टम सेटिंग"),
        ]
        for code, name, desc in role_rows:
            db.insert_and_get_id(conn, "roles", "role_id", ["role_code", "role_name", "description"], (code, name, desc))
        roles = {r["role_code"]: r["role_id"] for r in db.fetchall(conn, "SELECT * FROM roles")}
        default_users = [
            ("admin", "admin123", "प्रशासक", roles["ADMIN"]),
            ("eo", "eo123", "कार्यपालक अधिकारी", roles["EO_ADMIN"]),
            ("accountant", "acc123", "लेखाकार", roles["ACCOUNTANT"]),
            ("operator", "op123", "खाता संचालक", roles["ACCOUNT_OPERATOR"]),
        ]
        for username, pwd, full_name, role_id in default_users:
            db.insert_and_get_id(conn, "users", "user_id",
                ["username", "password_hash", "full_name", "role_id", "status"],
                (username, generate_password_hash(pwd), full_name, role_id, "ACTIVE"))
        conn.commit()
    conn.close()


bootstrap()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
