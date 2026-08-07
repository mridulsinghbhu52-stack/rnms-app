# -*- coding: utf-8 -*-
"""
RNMS — नगर पंचायत रतसर कलां वित्त एवं निर्माण कार्य प्रबंधन पोर्टल
Core MVP: Login/Roles -> मद/GO/आय -> कार्य/टेंडर/वर्क ऑर्डर -> बिल/भुगतान अनुमोदन -> कैशबुक
"""
import os
from datetime import datetime, date

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
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
    schemes = db.fetchall(conn, "SELECT * FROM schemes WHERE is_active = TRUE ORDER BY scheme_name")
    summary = []
    for s in schemes:
        opening = db.fetchone(conn, "SELECT COALESCE(SUM(amount),0) AS v FROM opening_balances WHERE scheme_id=?", (s["scheme_id"],))["v"]
        installments = db.fetchone(conn, "SELECT COALESCE(SUM(amount_received),0) AS v FROM installments WHERE scheme_id=?", (s["scheme_id"],))["v"]
        interest = db.fetchone(conn, "SELECT COALESCE(SUM(amount),0) AS v FROM bank_interest WHERE scheme_id=? AND (is_usable=TRUE)", (s["scheme_id"],))["v"]
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
         request.form.get("ifsc_code"), scheme_id, request.form.get("opening_date") or None, True))
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
                                WHERE scheme_id=? AND (is_active=TRUE OR is_active=TRUE)
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
        "schemes": db.fetchall(conn, "SELECT * FROM schemes WHERE is_active=TRUE OR is_active=TRUE ORDER BY scheme_name"),
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
    schemes = db.fetchall(conn, "SELECT * FROM schemes WHERE is_active=TRUE OR is_active=TRUE ORDER BY scheme_name")
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
    taxable_value = float(bill["amount_excl_gst"])
    no_deduction = bool(request.form.get("no_deduction"))
    include_cess = bool(request.form.get("include_labour_cess"))
    if no_deduction:
        cgst = sgst = income_tax = labour_cess = 0.0
    else:
        cgst = round(taxable_value * 0.01, 2)
        sgst = round(taxable_value * 0.01, 2)
        income_tax = round(taxable_value * 0.02, 2)
        labour_cess = round(taxable_value * 0.01, 2) if include_cess else 0.0
    total_deduction = round(cgst + sgst + income_tax + labour_cess, 2)
    net_payment = round(gross - total_deduction, 2)
    prior_posted = db.fetchone(conn, "SELECT COALESCE(SUM(net_payment),0) AS v FROM payments WHERE work_id=? AND status='POSTED'", (work["work_id"],))["v"]
    balance_sanction = round(float(work["estimated_amount"]) - float(prior_posted) - net_payment, 2)
    balance_l1 = round(float(latest_tender["l1_amount"]) - float(prior_posted) - net_payment, 2) if latest_tender and latest_tender["l1_amount"] else None

    bank_account_id = primary_bank_account(conn, work["scheme_id"])
    if not bank_account_id:
        conn.close()
        flash("इस मद हेतु कोई बैंक खाता सेट नहीं है – पहले Masters में बैंक खाता जोड़ें।", "error")
        return redirect(url_for("work_detail", work_id=work["work_id"]))

    payment_id = db.insert_and_get_id(conn, "payments", "payment_id",
        ["bill_id", "work_id", "gross_amount", "cgst_1pct", "sgst_1pct", "income_tax_2pct", "labour_cess_1pct",
         "no_deduction", "total_deduction", "net_payment", "balance_against_sanction", "balance_against_l1",
         "ppa_no", "ppa_date", "status", "entered_by", "posted_by", "posted_at", "remarks"],
        (bill_id, work["work_id"], gross, cgst, sgst, income_tax, labour_cess, no_deduction,
         total_deduction, net_payment, balance_sanction, balance_l1, request.form.get("ppa_no"),
         request.form.get("ppa_date") or None, "POSTED", session["user_id"], session["user_id"],
         datetime.now().isoformat(), request.form.get("remarks")))

    db.insert_and_get_id(conn, "payment_approval_log", "log_id",
        ["payment_id", "action", "actor_user_id", "remarks"],
        (payment_id, "ENTRY_AND_POST", session["user_id"], "Account Operator entry — सरल workflow (सीधे Posted)"))

    post_cashbook_entry(conn, bank_account_id, work["scheme_id"], today(),
                         f"भुगतान – {work['work_code']} / बिल {bill['bill_no']}",
                         payment=net_payment, reference_type="PAYMENT",
                         reference_id=payment_id, created_by=session["user_id"])
    db.run(conn, "UPDATE bills SET status='PAID' WHERE bill_id=?", (bill_id,))
    conn.commit()
    conn.close()
    flash(f"भुगतान पूर्ण हुआ – नेट राशि {fmt_amount(net_payment)}। अब 🖨️ Voucher प्रिंट करें।", "success")
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
        flash("इस मद हेतु कोई बैंक खाता सेट नहीं है – पहले Masters में बैंक खाता जोड़ें।", "error")
        return redirect(url_for("payments_queue"))
    cheque_number = request.form.get("cheque_number", "").strip()
    db.run(conn, "UPDATE payments SET status='POSTED', posted_by=?, posted_at=?, cheque_number=? WHERE payment_id=?",
           (session["user_id"], datetime.now().isoformat(), cheque_number, payment_id))
    db.insert_and_get_id(conn, "payment_approval_log", "log_id",
        ["payment_id", "action", "actor_user_id", "remarks"], (payment_id, "POST", session["user_id"], request.form.get("remarks")))
    post_cashbook_entry(conn, bank_account_id, work["scheme_id"], today(),
                         f"भुगतान – {work['work_code']} / बिल {bill['bill_no']}",
                         payment=float(payment["net_payment"]), reference_type="PAYMENT",
                         reference_id=payment_id, created_by=session["user_id"])
    db.run(conn, "UPDATE bills SET status='PAID' WHERE bill_id=?", (payment["bill_id"],))
    conn.commit()
    conn.close()
    flash("भुगतान Post हुआ एवं कैशबुक में दर्ज हुआ!", "success")
    return redirect(url_for("payments_queue"))



# ---------------------------------------------------------------------------
# Cashbook
# ---------------------------------------------------------------------------

# =============================================================================
# मौजूदा cashbook फ़ंक्शन को पूरा हटाकर यह पेस्ट करें
# (app.py में खोजें: "def cashbook():" — उसकी @app.route("/cashbook") और
#  @login_required लाइनों समेत, अगला @app.route शुरू होने से ठीक पहले तक)
# बदलाव: अब मदवार सारांश (कुल आय / कुल व्यय / शेष), प्रकार का कॉलम,
#         और प्रकार से छाँटने की सुविधा भी मिलेगी।
# =============================================================================

# =============================================================================
# मौजूदा cashbook फ़ंक्शन को पूरा हटाकर यह पेस्ट करें
# (app.py में खोजें: "def cashbook():" — उसकी @app.route("/cashbook") और
#  @login_required लाइनों समेत, अगला @app.route शुरू होने से ठीक पहले तक)
# बदलाव: अब मदवार सारांश (कुल आय / कुल व्यय / शेष), प्रकार का कॉलम,
#         और प्रकार से छाँटने की सुविधा भी मिलेगी।
# =============================================================================

# =============================================================================
# मौजूदा cashbook फ़ंक्शन को पूरा हटाकर यह पेस्ट करें
# (app.py में खोजें: "def cashbook():" — उसकी @app.route("/cashbook") और
#  @login_required लाइनों समेत, अगला @app.route शुरू होने से ठीक पहले तक)
# बदलाव: अब मदवार सारांश (कुल आय / कुल व्यय / शेष), प्रकार का कॉलम,
#         और प्रकार से छाँटने की सुविधा भी मिलेगी।
# =============================================================================

CASHBOOK_TYPE_LABELS = {
    "INSTALLMENT": "किस्त प्राप्त",
    "INTEREST": "बैंक ब्याज",
    "REFUND": "बैंक चार्ज वापसी",
    "OPENING": "आरम्भिक शेष",
    "PAYMENT": "ठेकेदार भुगतान",
    "TAX_REMITTANCE": "कटौती जमा (टैक्स)",
    "BANK_CHARGE": "बैंक चार्ज",
}

CASHBOOK_INCOME_TYPES = ["INSTALLMENT", "INTEREST", "REFUND", "OPENING"]
CASHBOOK_EXPENSE_TYPES = ["PAYMENT", "TAX_REMITTANCE", "BANK_CHARGE"]


@app.route("/cashbook")
@login_required
def cashbook():
    conn = db.get_db()
    scheme_id = request.args.get("scheme_id")
    ref_type = request.args.get("ref_type")

    where, params = [], []
    if scheme_id:
        where.append("c.scheme_id=?")
        params.append(scheme_id)
    if ref_type:
        where.append("c.reference_type=?")
        params.append(ref_type)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    entries = db.fetchall(conn, f"""SELECT c.*, s.scheme_name, ba.account_no FROM cashbook_entries c
                                    JOIN schemes s ON s.scheme_id=c.scheme_id
                                    JOIN bank_accounts ba ON ba.account_id=c.bank_account_id
                                    {where_sql}
                                    ORDER BY c.entry_date, c.entry_id""", tuple(params))

    swhere, sparams = [], []
    if scheme_id:
        swhere.append("c.scheme_id=?")
        sparams.append(scheme_id)
    swhere_sql = (" WHERE " + " AND ".join(swhere)) if swhere else ""
    summary = db.fetchall(conn, f"""SELECT s.scheme_id, s.scheme_name,
                                        COALESCE(SUM(c.receipt_amount),0) AS total_receipt,
                                        COALESCE(SUM(c.payment_amount),0) AS total_payment
                                    FROM cashbook_entries c JOIN schemes s ON s.scheme_id=c.scheme_id
                                    {swhere_sql}
                                    GROUP BY s.scheme_id, s.scheme_name
                                    ORDER BY s.scheme_name""", tuple(sparams))

    breakup = db.fetchall(conn, f"""SELECT c.reference_type AS rt,
                                        COALESCE(SUM(c.receipt_amount),0) AS total_receipt,
                                        COALESCE(SUM(c.payment_amount),0) AS total_payment
                                    FROM cashbook_entries c
                                    {swhere_sql}
                                    GROUP BY c.reference_type""", tuple(sparams))

    schemes = db.fetchall(conn, "SELECT * FROM schemes ORDER BY scheme_name")

    firm_map = {}
    for fr in db.fetchall(conn, """SELECT p.payment_id, f.firm_name
                                   FROM payments p JOIN bills b ON b.bill_id=p.bill_id
                                   JOIN firms f ON f.firm_id=b.firm_id"""):
        firm_map[fr["payment_id"]] = fr["firm_name"]
    conn.close()

    running = 0.0
    rows = []
    for e in entries:
        running += float(e["receipt_amount"] or 0) - float(e["payment_amount"] or 0)
        firm = firm_map.get(e["reference_id"]) if e["reference_type"] == "PAYMENT" else None
        rows.append({"e": e, "balance": round(running, 2), "firm": firm,
                     "label": CASHBOOK_TYPE_LABELS.get(e["reference_type"], e["reference_type"] or "—")})

    income_rows, expense_rows = [], []
    for b in breakup:
        label = CASHBOOK_TYPE_LABELS.get(b["rt"], b["rt"] or "अन्य")
        if float(b["total_receipt"] or 0):
            income_rows.append({"label": label, "amount": float(b["total_receipt"])})
        if float(b["total_payment"] or 0):
            expense_rows.append({"label": label, "amount": float(b["total_payment"])})

    grand_receipt = round(sum(float(x["total_receipt"] or 0) for x in summary), 2)
    grand_payment = round(sum(float(x["total_payment"] or 0) for x in summary), 2)

    return render_template("cashbook.html", rows=rows, schemes=schemes,
                            selected_scheme=scheme_id, ref_type=ref_type,
                            summary=summary, income_rows=income_rows, expense_rows=expense_rows,
                            grand_receipt=grand_receipt, grand_payment=grand_payment,
                            type_labels=CASHBOOK_TYPE_LABELS)





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

# =============================================================================
# RNMS — MASTER FILE — इस पूरी फ़ाइल की सामग्री अपने app.py के सबसे नीचे
# पेस्ट करें (अगर फ़ाइल के अंत में "if __name__ == "__main__":" जैसी कोई
# लाइन है, तो उससे पहले)। इसमें तीन चीज़ें हैं:
#   भाग A — Bulk Legacy-Import Module (95 कार्य + 10 GO डालने के लिए)
#   भाग B — Documents Module (GO/Estimate/Photo/Tender/Agreement/MB/Voucher अपलोड)
#
# ⚠️ याद रखें — new_payment() वाला भुगतान-गणना सुधार यहां नहीं है, वह अलग से
# "fix_payment_deduction.py" में है क्योंकि वह मौजूदा फ़ंक्शन को REPLACE करता
# है, यहां जोड़ने वाली बात नहीं है (MASTER_GUIDE.md में चरण 5 देखें)।
#
# ⚠️ पेस्ट करने से पहले अपने app.py की शुरुआत में देख लें:
#   1. "from flask import ..." में "jsonify" शामिल है क्या? नहीं है तो जोड़ दें।
#   2. अगर पहले से "import csv" या "import io" है तो नीचे वाली डुप्लीकेट लाइनें
#      हटा सकते हैं (दोबारा import करना भी सुरक्षित है, ज़रूरी नहीं)।
#   3. @require_role(...) में इस्तेमाल हुए role names (ADMIN, EO,
#      ACCOUNT_OPERATOR, JE) अपने असली role names से मिला लें।
# =============================================================================

import csv
import io
import storage_r2

# #############################################################################
# भाग A — Bulk Legacy-Import Module (Admin only)
# #############################################################################

SEED_SCHEMES = [
    # code,      name,                                              category,                      interest_usable, non_tender_allowed
    ("CMNSY",  "मुख्यमंत्री नगर सृजन योजना",                         "STATE_SCHEME",              False, False),
    ("CMVNY",  "मुख्यमंत्री वैश्विक नगरोदय योजना",                    "STATE_SCHEME",              False, False),
    ("AAK",    "आकांक्षी नगर योजना",                                 "STATE_SCHEME",              False, False),
    ("ADARSH", "पं. दीनदयाल/आदर्श नगर योजना",                         "STATE_SCHEME",              False, False),
    ("ANTYESHTI", "अन्त्येष्टि स्थल योजना",                          "STATE_SCHEME",              False, False),
    ("TALAB",  "तालाब/झील/पोखरा संरक्षण योजना",                       "STATE_SCHEME",              False, False),
    ("PEYJAL", "पेयजल योजना",                                        "STATE_SCHEME",              False, False),
    ("SFC",    "राज्य वित्त आयोग",                                    "STATE_FINANCE_COMMISSION",  True,  True),
    ("CFC",    "केन्द्रीय वित्त आयोग — Tied/Untied",                   "CENTRAL_FINANCE_COMMISSION",True,  False),
    ("NIKAY",  "निकाय निधि",                                         "NIKAY_NIDHI",                True,  True),
    ("OTHER",  "अन्य स्वीकृत मद/योजना",                                "OTHER",                      False, False),
]

SEED_FY = [
    # fy_name,   start_date,   end_date,     is_current
    ("2022-23", "2022-04-01", "2023-03-31", False),
    ("2023-24", "2023-04-01", "2024-03-31", False),
    ("2024-25", "2024-04-01", "2025-03-31", False),
    ("2025-26", "2025-04-01", "2026-03-31", False),
    ("2026-27", "2026-04-01", "2027-03-31", True),   # आज की तारीख (अगस्त 2026) इसी वित्तीय वर्ष में है
]


@app.route("/admin/import", methods=["GET"])
@require_role("ADMIN")
def import_home():
    conn = db.get_db()
    scheme_count = db.fetchone(conn, "SELECT COUNT(*) AS c FROM schemes")["c"]
    fy_count = db.fetchone(conn, "SELECT COUNT(*) AS c FROM financial_years")["c"]
    go_count = db.fetchone(conn, "SELECT COUNT(*) AS c FROM go_register")["c"]
    work_count = db.fetchone(conn, "SELECT COUNT(*) AS c FROM works")["c"]
    conn.close()
    return render_template("admin_import.html", scheme_count=scheme_count, fy_count=fy_count,
                            go_count=go_count, work_count=work_count)


@app.route("/admin/import/seed-masters", methods=["POST"])
@require_role("ADMIN")
def import_seed_masters():
    conn = db.get_db()
    added_schemes = added_fy = 0
    for code, name, category, interest_usable, non_tender_allowed in SEED_SCHEMES:
        existing = db.fetchone(conn, "SELECT scheme_id FROM schemes WHERE scheme_code=?", (code,))
        if not existing:
            db.insert_and_get_id(conn, "schemes", "scheme_id",
                ["scheme_code", "scheme_name", "scheme_category", "interest_usable", "non_tender_allowed"],
                (code, name, category, interest_usable, non_tender_allowed))
            added_schemes += 1
    for fy_name, start_date, end_date, is_current in SEED_FY:
        existing = db.fetchone(conn, "SELECT fy_id FROM financial_years WHERE fy_name=?", (fy_name,))
        if not existing:
            db.insert_and_get_id(conn, "financial_years", "fy_id",
                ["fy_name", "start_date", "end_date", "is_current"],
                (fy_name, start_date, end_date, is_current))
            added_fy += 1
    conn.close()
    flash(f"Master seed पूर्ण — {added_schemes} नई योजना, {added_fy} नए वित्तीय वर्ष जोड़े गए (पहले से मौजूद को छोड़कर)।", "success")
    return redirect(url_for("import_home"))


def _find_or_create_firm(conn, firm_name):
    firm_name = (firm_name or "").strip()
    if not firm_name:
        return None
    existing = db.fetchone(conn, "SELECT firm_id FROM firms WHERE firm_name=?", (firm_name,))
    if existing:
        return existing["firm_id"]
    return db.insert_and_get_id(conn, "firms", "firm_id", ["firm_name", "status"], (firm_name, "ACTIVE"))


@app.route("/admin/import/go", methods=["POST"])
@require_role("ADMIN")
def import_go():
    file = request.files.get("csv_file")
    if not file or not file.filename:
        flash("कृपया GO Master CSV फ़ाइल चुनें।", "error")
        return redirect(url_for("import_home"))

    stream = io.StringIO(file.stream.read().decode("utf-8-sig"))
    reader = csv.DictReader(stream)
    conn = db.get_db()
    created, skipped_existing, errors = 0, 0, []

    for i, row in enumerate(reader, start=2):  # पंक्ति 1 = header
        try:
            scheme = db.fetchone(conn, "SELECT scheme_id FROM schemes WHERE scheme_code=?", (row["scheme_code"].strip(),))
            if not scheme:
                errors.append(f"पंक्ति {i}: योजना कोड '{row['scheme_code']}' नहीं मिला — पहले 'Seed Schemes/FY' चलाएँ।")
                continue
            fy = db.fetchone(conn, "SELECT fy_id FROM financial_years WHERE fy_name=?", (row["fy_name"].strip(),))
            if not fy:
                errors.append(f"पंक्ति {i}: वित्तीय वर्ष '{row['fy_name']}' नहीं मिला।")
                continue
            existing_go = db.fetchone(conn, "SELECT go_id FROM go_register WHERE scheme_id=? AND go_number=?",
                                       (scheme["scheme_id"], row["go_number"].strip()))
            if existing_go:
                skipped_existing += 1
                continue
            remarks = row.get("remarks", "")
            if row.get("go_date_is_placeholder", "").strip().upper() == "YES":
                remarks = (remarks + " | दिनांक अस्थायी (placeholder) है — असली शासनादेश दिनांक से पुष्टि करें।").strip(" |")
            db.insert_and_get_id(conn, "go_register", "go_id",
                ["scheme_id", "fy_id", "go_number", "go_date", "subject", "total_sanctioned_amount", "remarks", "created_by"],
                (scheme["scheme_id"], fy["fy_id"], row["go_number"].strip(), row["go_date"].strip(),
                 row.get("subject", ""), to_float(row["total_sanctioned_amount"]), remarks, session["user_id"]))
            created += 1
        except Exception as e:
            errors.append(f"पंक्ति {i}: त्रुटि — {e}")

    conn.close()
    flash(f"GO Import पूर्ण — {created} नए GO बने, {skipped_existing} पहले से मौजूद (छोड़े गए), {len(errors)} त्रुटियाँ।",
          "success" if not errors else "error")
    for e in errors[:20]:
        flash(e, "error")
    return redirect(url_for("import_home"))


@app.route("/admin/import/works", methods=["POST"])
@require_role("ADMIN")
def import_works():
    file = request.files.get("csv_file")
    if not file or not file.filename:
        flash("कृपया Works CSV फ़ाइल चुनें।", "error")
        return redirect(url_for("import_home"))

    stream = io.StringIO(file.stream.read().decode("utf-8-sig"))
    reader = csv.DictReader(stream)
    conn = db.get_db()
    created, skipped_existing, errors = 0, 0, []

    for i, row in enumerate(reader, start=2):
        try:
            work_code = row["work_code"].strip()
            existing_work = db.fetchone(conn, "SELECT work_id FROM works WHERE work_code=?", (work_code,))
            if existing_work:
                skipped_existing += 1
                continue

            scheme = db.fetchone(conn, "SELECT scheme_id FROM schemes WHERE scheme_code=?", (row["scheme_code"].strip(),))
            if not scheme:
                errors.append(f"पंक्ति {i} ({work_code}): योजना कोड '{row['scheme_code']}' नहीं मिला।")
                continue
            fy = db.fetchone(conn, "SELECT fy_id FROM financial_years WHERE fy_name=?", (row["fy_name"].strip(),))
            if not fy:
                errors.append(f"पंक्ति {i} ({work_code}): वित्तीय वर्ष '{row['fy_name']}' नहीं मिला।")
                continue
            go = db.fetchone(conn, "SELECT go_id FROM go_register WHERE scheme_id=? AND go_number=?",
                              (scheme["scheme_id"], row["go_number"].strip()))
            if not go:
                errors.append(f"पंक्ति {i} ({work_code}): संबंधित GO '{row['go_number']}' नहीं मिला — पहले GO Import चलाएँ।")
                continue

            ward_id = None
            if row.get("ward_no", "").strip():
                ward = db.fetchone(conn, "SELECT ward_id FROM wards WHERE ward_no=?", (row["ward_no"].strip(),))
                ward_id = ward["ward_id"] if ward else None

            asset_type_id = None
            if row.get("asset_type_name", "").strip():
                at = db.fetchone(conn, "SELECT asset_type_id FROM asset_types WHERE asset_type_name=?",
                                  (row["asset_type_name"].strip(),))
                asset_type_id = at["asset_type_id"] if at else None

            is_tendered = row.get("is_tendered", "TRUE").strip().upper() == "TRUE"

            work_id = db.insert_and_get_id(conn, "works", "work_id",
                ["work_code", "scheme_id", "ward_id", "fy_id", "asset_type_id", "work_name", "work_source",
                 "is_tendered", "estimated_amount", "status", "proposed_date", "created_by", "go_id", "remarks"],
                (work_code, scheme["scheme_id"], ward_id, fy["fy_id"], asset_type_id, row["work_name"],
                 row.get("work_source", "LEGACY"), is_tendered, to_float(row["estimated_amount"]),
                 row.get("status", "PROPOSED"), row["proposed_date"], session["user_id"], go["go_id"],
                 row.get("remarks", "")))
            created += 1

            l1_amount_raw = row.get("l1_amount", "").strip()
            if l1_amount_raw:
                firm_id = _find_or_create_firm(conn, row.get("firm_name", ""))
                tender_no = f"LEGACY-{work_code}"
                remarks_t = "दिनांक/टेंडर-संख्या अस्थायी (placeholder) है — असली टेंडर अभिलेख से पुष्टि करें।"
                db.insert_and_get_id(conn, "tenders", "tender_id",
                    ["work_id", "tender_no", "tender_date", "tender_amount", "l1_firm_id", "l1_amount", "status",
                     "remarks", "created_by"],
                    (work_id, tender_no, row["proposed_date"], to_float(row["estimated_amount"]), firm_id,
                     to_float(l1_amount_raw), "AWARDED", remarks_t, session["user_id"]))
        except Exception as e:
            errors.append(f"पंक्ति {i}: त्रुटि — {e}")

    conn.commit()
    conn.close()
    flash(f"Works Import पूर्ण — {created} नए कार्य बने, {skipped_existing} पहले से मौजूद (छोड़े गए), {len(errors)} त्रुटियाँ।",
          "success" if not errors else "error")
    for e in errors[:20]:
        flash(e, "error")
    return redirect(url_for("import_home"))


# #############################################################################
# भाग B — Documents Module (GO/Estimate/Photo/Tender/Agreement/MB/Voucher)
# #############################################################################

DOC_CATEGORY_MAP = {"TENDER_NOTICE": [
        ("NOTICE_DOC", "निविदा दस्तावेज़ (NIT)"),
        ("PUBLICATION", "सूचना प्रकाशन (अख़बार कतरन)"),
        ("EPROC", "e-Tender पोर्टल प्रति / रसीद"),
        ("TECH_BID_RECORD", "तकनीकी बिड अभिलेख"),
        ("FIN_BID_RECORD", "वित्तीय बिड अभिलेख"),
        ("OTHER", "अन्य"),
    ],
    "GO": [
        ("GO_ORDER", "शासनादेश (GO) स्कैन कॉपी"),
    ],
    "WORK": [
        ("ESTIMATE", "प्राक्कलन (Estimate)"),
        ("PHOTO_BEFORE", "फोटो - कार्य से पहले"),
        ("PHOTO_PROGRESS", "फोटो - कार्य प्रगति के दौरान"),
        ("PHOTO_AFTER", "फोटो - कार्य पूर्ण होने पर"),
    ],
    "TENDER": [
        ("TENDER_NOTICE", "निविदा सूचना"),
        ("EMD", "धरोहर राशि (EMD) रसीद"),
        ("L1_COMPARATIVE", "L1 तुलनात्मक विवरण"),("L1_PAPERS", "L1 के हार्ड पेपर"),
        ("EMD_BANK_VERIFY", "EMD बैंक सत्यापन"),
        ("WORK_ORDER", "कार्यादेश (Work Order)"),
        ("AGREEMENT", "अनुबंध (Agreement)"),
    ],
    "BILL": [
    ("MEASUREMENT_BOOK", "माप पुस्तिका (MB)"),
     ("INSPECTION_REPORT", "जांच रिपोर्ट"),
     ("TEST_REPORT", "टेस्ट रिपोर्ट"),
        ("BILL_COPY", "बिल की प्रति"),
    ],
    "PAYMENT": [
        ("VOUCHER", "भुगतान नोटिंग / वाउचर"),
        ("PAYMENT_PROOF", "भुगतान प्रमाण (UTR/चेक स्कैन)"),
    ],
}


@app.context_processor
def inject_doc_categories():
    return {"doc_categories": DOC_CATEGORY_MAP}


@app.route("/documents/upload/<related_type>/<int:related_id>", methods=["POST"])
@require_role("ADMIN", "EO_ADMIN", "ACCOUNTANT", "ACCOUNT_OPERATOR")
def upload_document(related_type, related_id):
    related_type = related_type.upper()
    if related_type not in DOC_CATEGORY_MAP:
        flash("अमान्य दस्तावेज़ श्रेणी", "danger")
        return redirect(request.referrer or url_for("dashboard"))

    doc_category = request.form.get("doc_category")
    valid_categories = [c[0] for c in DOC_CATEGORY_MAP[related_type]]
    if doc_category not in valid_categories:
        flash("अमान्य दस्तावेज़ प्रकार", "danger")
        return redirect(request.referrer or url_for("dashboard"))

    file = request.files.get("file")
    if not file or file.filename == "":
        flash("कोई फ़ाइल नहीं चुनी गई", "warning")
        return redirect(request.referrer or url_for("dashboard"))

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in storage_r2.ALLOWED_EXTENSIONS:
        flash("केवल PDF, JPG, PNG फ़ाइलें स्वीकार हैं", "danger")
        return redirect(request.referrer or url_for("dashboard"))

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > storage_r2.MAX_FILE_SIZE_BYTES:
        flash("फ़ाइल 15 MB से बड़ी है", "danger")
        return redirect(request.referrer or url_for("dashboard"))

    object_key = storage_r2.upload_file(file, related_type, related_id, doc_category)

    conn = db.get_db()
    db.insert_and_get_id(
        conn, "documents", "document_id",
        ["related_type", "related_id", "doc_category", "original_filename",
         "object_key", "file_size_bytes", "uploaded_by"],
        (related_type, related_id, doc_category, file.filename, object_key, size, session["user_id"]),
    )
    conn.commit()
    conn.close()
    flash("दस्तावेज़ सफलतापूर्वक अपलोड हुआ", "success")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/documents/api/<related_type>/<int:related_id>")
@require_role("ADMIN", "EO_ADMIN", "ACCOUNTANT", "ACCOUNT_OPERATOR")
def api_list_documents(related_type, related_id):
    related_type = related_type.upper()
    conn = db.get_db()
    docs = db.fetchall(
        conn, "SELECT * FROM documents WHERE related_type=? AND related_id=? ORDER BY uploaded_at DESC",
        (related_type, related_id),
    )
    conn.close()
    label_map = dict(DOC_CATEGORY_MAP.get(related_type, []))
    result = [{
        "document_id": d["document_id"],
        "doc_category": d["doc_category"],
        "doc_category_label": label_map.get(d["doc_category"], d["doc_category"]),
        "original_filename": d["original_filename"],
        "uploaded_at": str(d["uploaded_at"]),
    } for d in docs]
    return jsonify(result)


@app.route("/documents/manage/<related_type>/<int:related_id>")
@require_role("ADMIN", "EO_ADMIN", "ACCOUNTANT", "ACCOUNT_OPERATOR")
def manage_documents(related_type, related_id):
    related_type = related_type.upper()
    if related_type not in DOC_CATEGORY_MAP:
        flash("अमान्य दस्तावेज़ श्रेणी", "danger")
        return redirect(url_for("dashboard"))
    return render_template("documents_manage.html", related_type=related_type, related_id=related_id)  
@app.route("/documents/<int:document_id>/download")
@require_role("ADMIN", "EO_ADMIN", "ACCOUNTANT", "ACCOUNT_OPERATOR")
def download_document(document_id):
    conn = db.get_db()
    doc = db.fetchone(conn, "SELECT * FROM documents WHERE document_id=?", (document_id,))
    conn.close()
    if not doc:
        flash("दस्तावेज़ नहीं मिला", "danger")
        return redirect(url_for("dashboard"))
    url = storage_r2.get_download_url(doc["object_key"])
    return redirect(url)


@app.route("/documents/<int:document_id>/delete", methods=["POST"])
@require_role("ADMIN")
def delete_document(document_id):
    conn = db.get_db()
    doc = db.fetchone(conn, "SELECT * FROM documents WHERE document_id=?", (document_id,))
    if not doc:
        flash("दस्तावेज़ नहीं मिला", "danger")
        return redirect(url_for("dashboard"))
    storage_r2.delete_file(doc["object_key"])
    db.run(conn, "DELETE FROM documents WHERE document_id=?", (document_id,))
    conn.commit()
    conn.close()
    flash("दस्तावेज़ हटाया गया", "success")
    return redirect(request.referrer or url_for("dashboard"))

# =============================================================================
# चरण B — app.py के सबसे नीचे (if __name__ == "__main__": से पहले) पेस्ट करें
# यह Voucher Print + Tax Remittance (GST/आयकर/Labour Cess जमा ट्रैकिंग) का पूरा कोड है।
# =============================================================================

# -----------------------------------------------------------------------------
# Payment Voucher Print
# -----------------------------------------------------------------------------

@app.route("/payments/<int:payment_id>/voucher")
@login_required
def payment_voucher(payment_id):
    conn = db.get_db()
    payment = db.fetchone(conn, """SELECT p.*, w.work_code, w.work_name, s.scheme_name,
                                    b.bill_no, b.bill_date, f.firm_name, f.pan_no, f.gst_no,
                                    f.bank_account_no, f.bank_ifsc, f.bank_name
                             FROM payments p
                             JOIN works w ON w.work_id=p.work_id
                             JOIN schemes s ON s.scheme_id=w.scheme_id
                             JOIN bills b ON b.bill_id=p.bill_id
                             JOIN firms f ON f.firm_id=b.firm_id
                             WHERE p.payment_id=?""", (payment_id,))
    conn.close()
    if not payment:
        flash("भुगतान नहीं मिला", "error")
        return redirect(url_for("payments_queue"))
    return render_template("payment_voucher.html", payment=payment)


# -----------------------------------------------------------------------------
# Tax Remittance Reconciliation — GST / आयकर / Labour Cess सरकार को जमा ट्रैकिंग
# (महीने-वार consolidated — जैसा आपने बताया)
# -----------------------------------------------------------------------------

def _month_range(period_month):
    y, m = map(int, period_month.split("-"))
    start = f"{y:04d}-{m:02d}-01"
    if m == 12:
        end = f"{y+1:04d}-01-01"
    else:
        end = f"{y:04d}-{m+1:02d}-01"
    return start, end

TAX_TYPE_COL = {"GST": "gst_remittance_id", "INCOME_TAX": "income_tax_remittance_id", "LABOUR_CESS": "labour_cess_remittance_id"}
TAX_TYPE_AMOUNT_EXPR = {"GST": "(p.cgst_1pct + p.sgst_1pct)", "INCOME_TAX": "p.income_tax_2pct", "LABOUR_CESS": "p.labour_cess_1pct"}
TAX_TYPE_LABELS = [("GST", "GST (CGST+SGST)"), ("INCOME_TAX", "आयकर (TDS)"), ("LABOUR_CESS", "Labour Cess")]


@app.route("/tax-remittance")
@require_role("ACCOUNTANT", "ADMIN")
def tax_remittance_home():
    conn = db.get_db()
    period_month = request.args.get("period_month") or today()[:7]
    tax_type = request.args.get("tax_type") or "GST"
    col = TAX_TYPE_COL.get(tax_type, "gst_remittance_id")
    amt = TAX_TYPE_AMOUNT_EXPR.get(tax_type, "(p.cgst_1pct + p.sgst_1pct)")
    start, end = _month_range(period_month)
    payments = db.fetchall(conn, f"""SELECT p.payment_id, p.status, p.posted_at, {amt} AS tax_amount, p.{col} AS remittance_id,
                                    w.work_code, b.bill_no, f.firm_name, f.pan_no
                             FROM payments p
                             JOIN works w ON w.work_id=p.work_id
                             JOIN bills b ON b.bill_id=p.bill_id
                             JOIN firms f ON f.firm_id=b.firm_id
                             WHERE p.status='POSTED' AND p.posted_at>=? AND p.posted_at<?
                             ORDER BY p.posted_at""", (start, end))
    remittances = db.fetchall(conn, "SELECT * FROM tax_remittances WHERE tax_type=? AND period_month=? ORDER BY remittance_id DESC",
                               (tax_type, period_month))
    conn.close()
    return render_template("tax_remittance.html", payments=payments, remittances=remittances,
                            period_month=period_month, tax_type=tax_type, tax_types=TAX_TYPE_LABELS)


# =============================================================================
# मौजूदा create_tax_remittance फ़ंक्शन को पूरा हटाकर यह पेस्ट करें
# (app.py में खोजें: "def create_tax_remittance" — उसकी @app.route/@require_role
#  लाइनों समेत, अगला @app.route शुरू होने से ठीक पहले तक)
# बदलाव: अब टैक्स जमा करने पर कैशबुक में भी "व्यय" की एंट्री बनेगी (मदवार अलग-अलग)
# =============================================================================

@app.route("/tax-remittance/create", methods=["POST"])
@require_role("ACCOUNTANT", "ADMIN")
def create_tax_remittance():
    conn = db.get_db()
    tax_type = request.form.get("tax_type")
    period_month = request.form.get("period_month")
    cheque_number = request.form.get("cheque_number", "").strip()
    remittance_date = request.form.get("remittance_date")
    remarks = request.form.get("remarks", "")
    payment_ids = request.form.getlist("payment_ids")
    col = TAX_TYPE_COL.get(tax_type)
    amt_expr = {"GST": "(cgst_1pct + sgst_1pct)", "INCOME_TAX": "income_tax_2pct", "LABOUR_CESS": "labour_cess_1pct"}.get(tax_type)
    if not col or not payment_ids:
        conn.close()
        flash("कृपया कम से कम एक भुगतान चुनें।", "error")
        return redirect(url_for("tax_remittance_home", period_month=period_month, tax_type=tax_type))
    total = 0.0
    for pid in payment_ids:
        row = db.fetchone(conn, f"SELECT {amt_expr} AS amt FROM payments WHERE payment_id=?", (pid,))
        total += float(row["amt"]) if row and row["amt"] else 0.0
    remittance_id = db.insert_and_get_id(conn, "tax_remittances", "remittance_id",
        ["tax_type", "period_month", "total_amount", "cheque_number", "remittance_date", "remarks", "created_by"],
        (tax_type, period_month, round(total, 2), cheque_number, remittance_date, remarks, session["user_id"]))
    for pid in payment_ids:
        db.run(conn, f"UPDATE payments SET {col}=? WHERE payment_id=?", (remittance_id, pid))

    # ---- कैशबुक में व्यय की एंट्री — प्रत्येक मद (योजना) के लिए अलग ----
    tax_label = dict(TAX_TYPE_LABELS).get(tax_type, tax_type)
    scheme_totals = {}
    for pid in payment_ids:
        row = db.fetchone(conn, f"""SELECT w.scheme_id AS sid, {amt_expr} AS amt
                                    FROM payments p JOIN works w ON w.work_id=p.work_id
                                    WHERE p.payment_id=?""", (pid,))
        if row and row["amt"]:
            scheme_totals[row["sid"]] = scheme_totals.get(row["sid"], 0.0) + float(row["amt"])
    for sid, amt in scheme_totals.items():
        bank_account_id = primary_bank_account(conn, sid)
        if bank_account_id and amt:
            post_cashbook_entry(conn, bank_account_id, sid, remittance_date or today(),
                                 f"कटौती जमा – {tax_label} (माह {period_month})" +
                                 (f" / चालान-चेक {cheque_number}" if cheque_number else ""),
                                 payment=round(amt, 2), reference_type="TAX_REMITTANCE",
                                 reference_id=remittance_id, created_by=session["user_id"])

    conn.commit()
    conn.close()
    flash(f"जमा रिकॉर्ड बना — {len(payment_ids)} भुगतान जोड़े गए, कुल राशि {round(total,2)} (कैशबुक में भी दर्ज)", "success")
    return redirect(url_for("tax_remittance_home", period_month=period_month, tax_type=tax_type))

# =============================================================================
# app.py के सबसे नीचे (if __name__ == "__main__": से पहले) पेस्ट करें
# यह नया route है — भुगतान बनने के बाद, चेक कटने पर, चेक नंबर बाद में जोड़ने के लिए
# (क्योंकि अब भुगतान बनते ही Post हो जाता है, इसलिए चेक नंबर उस समय पता नहीं होता)
# =============================================================================

@app.route("/payments/<int:payment_id>/cheque", methods=["POST"])
@require_role("ACCOUNT_OPERATOR", "ACCOUNTANT", "ADMIN")
def update_payment_cheque(payment_id):
    conn = db.get_db()
    cheque_number = request.form.get("cheque_number", "").strip()
    db.run(conn, "UPDATE payments SET cheque_number=? WHERE payment_id=?", (cheque_number, payment_id))
    conn.commit()
    conn.close()
    flash("चेक नंबर अपडेट हुआ।", "success")
    return redirect(request.referrer or url_for("payments_queue"))
# =============================================================================
# app.py के सबसे नीचे (if __name__ == "__main__": से पहले) पेस्ट करें
# यह "पत्रावली नोटिंग" (Office Note) प्रिंट फ़ॉर्मेट का पूरा कोड है —
# साथ में हिंदी में राशि शब्दों में लिखने वाला converter भी।
# =============================================================================

HINDI_ONES = [
    "", "एक", "दो", "तीन", "चार", "पाँच", "छह", "सात", "आठ", "नौ",
    "दस", "ग्यारह", "बारह", "तेरह", "चौदह", "पंद्रह", "सोलह", "सत्रह", "अठारह", "उन्नीस",
    "बीस", "इक्कीस", "बाईस", "तेईस", "चौबीस", "पच्चीस", "छब्बीस", "सत्ताईस", "अट्ठाईस", "उनतीस",
    "तीस", "इकतीस", "बत्तीस", "तैंतीस", "चौंतीस", "पैंतीस", "छत्तीस", "सैंतीस", "अड़तीस", "उनतालीस",
    "चालीस", "इकतालीस", "बयालीस", "तैंतालीस", "चौवालीस", "पैंतालीस", "छियालीस", "सैंतालीस", "अड़तालीस", "उनचास",
    "पचास", "इक्यावन", "बावन", "तिरेपन", "चौवन", "पचपन", "छप्पन", "सत्तावन", "अट्ठावन", "उनसठ",
    "साठ", "इकसठ", "बासठ", "तिरेसठ", "चौंसठ", "पैंसठ", "छियासठ", "सड़सठ", "अड़सठ", "उनहत्तर",
    "सत्तर", "इकहत्तर", "बहत्तर", "तिहत्तर", "चौहत्तर", "पचहत्तर", "छिहत्तर", "सतहत्तर", "अठहत्तर", "उन्यासी",
    "अस्सी", "इक्यासी", "बयासी", "तिरासी", "चौरासी", "पचासी", "छियासी", "सत्तासी", "अट्ठासी", "नवासी",
    "नब्बे", "इक्यानबे", "बानबे", "तिरानबे", "चौरानबे", "पंचानबे", "छियानबे", "सत्तानबे", "अट्ठानबे", "निन्यानबे",
]

HINDI_ORDINALS = ["", "प्रथम", "द्वितीय", "तृतीय", "चतुर्थ", "पंचम", "षष्ठम", "सप्तम", "अष्टम", "नवम", "दशम"]


def _hindi_below_thousand(n):
    parts = []
    if n >= 100:
        parts.append(HINDI_ONES[n // 100] + " सौ")
        n = n % 100
    if n:
        parts.append(HINDI_ONES[n])
    return " ".join(parts)


def hindi_number_words(n):
    n = int(n)
    if n == 0:
        return "शून्य"
    parts = []
    crore = n // 10000000
    n = n % 10000000
    lakh = n // 100000
    n = n % 100000
    thousand = n // 1000
    n = n % 1000
    if crore:
        parts.append(hindi_number_words(crore) + " करोड़")
    if lakh:
        parts.append(_hindi_below_thousand(lakh) + " लाख")
    if thousand:
        parts.append(_hindi_below_thousand(thousand) + " हजार")
    if n:
        parts.append(_hindi_below_thousand(n))
    return " ".join(parts)


def hindi_amount_words(amount):
    try:
        amount = float(amount or 0)
    except (TypeError, ValueError):
        return ""
    rupees = int(amount)
    paise = int(round((amount - rupees) * 100))
    if paise:
        return f"{hindi_number_words(rupees)} रुपये {hindi_number_words(paise)} पैसे मात्र"
    return f"{hindi_number_words(rupees)} रुपये मात्र"


app.jinja_env.filters["hword"] = hindi_amount_words


def _ddmmyyyy(value):
    if not value:
        return ""
    s = str(value)[:10]
    parts = s.split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return s


@app.route("/payments/<int:payment_id>/noting")
@login_required
def payment_noting(payment_id):
    conn = db.get_db()
    payment = db.fetchone(conn, """SELECT p.*, w.work_code, w.work_name, w.work_id AS w_id,
                                    s.scheme_name, b.bill_no, b.bill_date, b.amount_excl_gst,
                                    b.amount_incl_gst, b.gst_rate, f.firm_name, f.pan_no, f.gst_no
                             FROM payments p
                             JOIN works w ON w.work_id=p.work_id
                             JOIN schemes s ON s.scheme_id=w.scheme_id
                             JOIN bills b ON b.bill_id=p.bill_id
                             JOIN firms f ON f.firm_id=b.firm_id
                             WHERE p.payment_id=?""", (payment_id,))
    if not payment:
        conn.close()
        flash("भुगतान नहीं मिला", "error")
        return redirect(url_for("payments_queue"))

    seq_row = db.fetchone(conn, "SELECT COUNT(*) AS c FROM bills WHERE work_id=? AND bill_id<=?",
                          (payment["work_id"], payment["bill_id"]))
    seq = int(seq_row["c"]) if seq_row else 1
    bill_ordinal = HINDI_ORDINALS[seq] if 0 < seq < len(HINDI_ORDINALS) else f"{seq}वाँ"

    wo_date_str = ""
    try:
        wo = db.fetchone(conn, "SELECT * FROM work_orders WHERE work_id=? ORDER BY wo_id DESC LIMIT 1",
                         (payment["work_id"],))
        if wo:
            for key in ("wo_date", "work_order_date", "order_date"):
                try:
                    if wo[key]:
                        wo_date_str = _ddmmyyyy(wo[key])
                        break
                except Exception:
                    continue
    except Exception:
        wo_date_str = ""

    conn.close()

    gst_amount = round(float(payment["amount_incl_gst"] or 0) - float(payment["amount_excl_gst"] or 0), 2)

    return render_template("payment_noting.html", p=payment, gst_amount=gst_amount,
                            bill_ordinal=bill_ordinal, wo_date_str=wo_date_str,
                            bill_date_str=_ddmmyyyy(payment["bill_date"]))
# =============================================================================
# app.py के सबसे नीचे (if __name__ == "__main__": से पहले) पेस्ट करें
# यह "महीने-वार टैक्स कटौती सूची — चालान हेतु प्रिंट" वाला नया route है।
# =============================================================================

@app.route("/tax-remittance/print")
@require_role("ACCOUNTANT", "ADMIN")
def tax_remittance_print():
    tax_type = request.args.get("tax_type") or "GST"
    period_month = request.args.get("period_month") or today()[:7]
    amt = TAX_TYPE_AMOUNT_EXPR.get(tax_type, "(p.cgst_1pct + p.sgst_1pct)")
    col = TAX_TYPE_COL.get(tax_type, "gst_remittance_id")
    start, end = _month_range(period_month)

    conn = db.get_db()
    rows = db.fetchall(conn, f"""SELECT p.payment_id, {amt} AS tax_amount, p.{col} AS remittance_id,
                                    p.cheque_number, w.work_code, w.work_name,
                                    b.bill_no, b.bill_date, b.amount_excl_gst,
                                    f.firm_name, f.pan_no, f.gst_no
                             FROM payments p
                             JOIN works w ON w.work_id=p.work_id
                             JOIN bills b ON b.bill_id=p.bill_id
                             JOIN firms f ON f.firm_id=b.firm_id
                             WHERE p.status='POSTED' AND p.posted_at>=? AND p.posted_at<?
                             ORDER BY p.payment_id""", (start, end))
    conn.close()

    total = round(sum(float(r["tax_amount"] or 0) for r in rows), 2)
    tax_label = dict(TAX_TYPE_LABELS).get(tax_type, tax_type)

    return render_template("tax_remittance_print.html", rows=rows, total=total,
                            tax_type=tax_type, tax_label=tax_label, period_month=period_month)
# =============================================================================
# app.py के सबसे नीचे (if __name__ == "__main__": से पहले) पेस्ट करें
# यह पूरा "निविदा (Tender)" सेक्शन है — निविदा सूचना, उसमें शामिल कार्य,
# EMD/टेंडर फीस, तकनीकी-वित्तीय बिड, L1, एग्रीमेंट व कार्यादेश।
# =============================================================================

from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING

EMD_PERCENT = 0.10           # धरोहर राशि — टेंडर धनराशि का 10%
TENDER_GST_RATE = 0.18       # टेंडर धनराशि + 18% = स्वीकृत धनराशि
TENDER_FEE_PER_LAKH = 100.0  # निविदा प्रपत्र शुल्क — प्रति लाख ₹100, फिर उस पर 18% GST


def _round_rupee(value):
    """पूर्णांक रुपये — 0.49 नीचे, 0.50 ऊपर"""
    try:
        return float(Decimal(str(float(value or 0))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception:
        return 0.0


def _ceil_to(value, step):
    """ऊपर की ओर पूर्णांक — जैसे 336271.20 को 1000 में → 337000"""
    try:
        v = Decimal(str(float(value or 0))) / Decimal(str(step))
        return float(v.quantize(Decimal("1"), rounding=ROUND_CEILING) * Decimal(str(step)))
    except Exception:
        return 0.0


def _excl_gst(amount):
    """स्वीकृत धनराशि से टेंडर धनराशि — टेंडर धनराशि × 1.18 = स्वीकृत धनराशि"""
    try:
        return _round_rupee(float(amount or 0) / (1 + TENDER_GST_RATE))
    except (TypeError, ValueError):
        return 0.0


def _emd_amount(excl_amount):
    """धरोहर राशि — टेंडर धनराशि का 10%, ऊपर की ओर ₹1,000 में पूर्णांक"""
    return _ceil_to(float(excl_amount or 0) * EMD_PERCENT, 1000)


def _tender_fee(excl_amount):
    """निविदा प्रपत्र शुल्क — ₹100 प्रति लाख (ऊपर ₹10 में पूर्णांक) + उस पर 18% GST"""
    try:
        base = _ceil_to(float(excl_amount or 0) / 100000.0 * TENDER_FEE_PER_LAKH, 10)
        return _round_rupee(base + base * TENDER_GST_RATE)
    except (TypeError, ValueError):
        return 0.0


NOTICE_STATUS_LABELS = [
    ("PUBLISHED", "प्रकाशित"),
    ("TECHNICAL_OPENED", "तकनीकी बिड खुली"),
    ("FINANCIAL_OPENED", "वित्तीय बिड खुली"),
    ("AWARDED", "आवंटित (L1 तय)"),
    ("CANCELLED", "निरस्त"),
]

HINDI_MONTHS = ["", "जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून",
                "जुलाई", "अगस्त", "सितम्बर", "अक्टूबर", "नवम्बर", "दिसम्बर"]


def _hindi_date(value):
    """2025-05-19 → 19 मई, 2025"""
    if not value:
        return ""
    s = str(value)[:10].split("-")
    if len(s) != 3:
        return str(value)
    try:
        return f"{int(s[2])} {HINDI_MONTHS[int(s[1])]}, {s[0]}"
    except Exception:
        return str(value)


def _dmy(value):
    """2025-05-19 → 19.05.2025"""
    if not value:
        return ""
    s = str(value)[:10].split("-")
    return f"{s[2]}.{s[1]}.{s[0]}" if len(s) == 3 else str(value)


app.jinja_env.filters["hdate"] = _hindi_date
app.jinja_env.filters["dmy"] = _dmy


def _notice_form_values(form):
    scheme_id = form.get("scheme_id")
    return {
        "notice_no": form["notice_no"],
        "letter_no": form.get("letter_no"),
        "tender_type": form.get("tender_type") or "अल्पकालिक",
        "notice_date": form.get("notice_date") or None,
        "scheme_id": int(scheme_id) if scheme_id else None,
        "publish_date": form.get("publish_date") or None,
        "publish_time": form.get("publish_time"),
        "download_start_date": form.get("download_start_date") or None,
        "download_time": form.get("download_time"),
        "upload_start_date": form.get("upload_start_date") or None,
        "upload_start_time": form.get("upload_start_time"),
        "bid_last_date": form.get("bid_last_date") or None,
        "upload_last_time": form.get("upload_last_time"),
        "financial_open_date": form.get("financial_open_date") or None,
        "open_time": form.get("open_time"),
        "technical_open_date": form.get("technical_open_date") or None,
        "tender_no": form.get("tender_no"),
        "eproc_ref": form.get("eproc_ref"),
        "fee_bank_account_id": int(form["fee_bank_account_id"]) if form.get("fee_bank_account_id") else None,
        "remarks": form.get("remarks"),
    }


@app.route("/tenders")
@login_required
def tender_notices():
    conn = db.get_db()
    rows = db.fetchall(conn, """SELECT n.*, s.scheme_name,
                                   (SELECT COUNT(*) FROM tenders t WHERE t.notice_id=n.notice_id) AS work_count,
                                   (SELECT COALESCE(SUM(w.estimated_amount),0) FROM tenders t
                                      JOIN works w ON w.work_id=t.work_id
                                      WHERE t.notice_id=n.notice_id) AS total_amount
                            FROM tender_notices n
                            LEFT JOIN schemes s ON s.scheme_id=n.scheme_id
                            ORDER BY n.notice_id DESC""")
    schemes = db.fetchall(conn, "SELECT * FROM schemes ORDER BY scheme_name")
    accounts = db.fetchall(conn, """SELECT ba.*, s.scheme_name FROM bank_accounts ba
                                    LEFT JOIN schemes s ON s.scheme_id=ba.scheme_id
                                    ORDER BY ba.account_id""")
    gos = db.fetchall(conn, """SELECT go_id, scheme_id, go_number, go_date, govt_letter_ref
                               FROM go_register ORDER BY scheme_id, go_number""")
    gos = db.fetchall(conn, """SELECT go_id, scheme_id, go_number, go_date, govt_letter_ref
                               FROM go_register ORDER BY scheme_id, go_number""")
    conn.close()
    return render_template("tenders_list.html", rows=rows, schemes=schemes, accounts=accounts,gos=gos,
                            status_labels=dict(NOTICE_STATUS_LABELS))


@app.route("/tenders/new", methods=["POST"])
@require_role("ACCOUNT_OPERATOR", "ADMIN")
def new_tender_notice():
    conn = db.get_db()
    v = _notice_form_values(request.form)
    cols = list(v.keys()) + ["status", "created_by"]
    vals = tuple(list(v.values()) + ["PUBLISHED", session["user_id"]])
    notice_id = db.insert_and_get_id(conn, "tender_notices", "notice_id", cols, vals)
    conn.commit()
    conn.close()
    flash("निविदा सूचना दर्ज हुई। अब इसमें कार्य जोड़ें।", "success")
    return redirect(url_for("tender_notice_detail", notice_id=notice_id))


@app.route("/tenders/<int:notice_id>/update", methods=["POST"])
@require_role("ACCOUNT_OPERATOR", "ADMIN")
def update_tender_notice(notice_id):
    conn = db.get_db()
    v = _notice_form_values(request.form)
    v["status"] = request.form.get("status") or "PUBLISHED"
    sets = ", ".join(f"{k}=?" for k in v.keys())
    db.run(conn, f"UPDATE tender_notices SET {sets} WHERE notice_id=?", tuple(list(v.values()) + [notice_id]))
    conn.commit()
    conn.close()
    flash("निविदा सूचना अपडेट हुई।", "success")
    return redirect(url_for("tender_notice_detail", notice_id=notice_id))


@app.route("/tenders/<int:notice_id>")
@login_required
def tender_notice_detail(notice_id):
    conn = db.get_db()
    notice = db.fetchone(conn, """SELECT n.*, s.scheme_name FROM tender_notices n
                                  LEFT JOIN schemes s ON s.scheme_id=n.scheme_id
                                  WHERE n.notice_id=?""", (notice_id,))
    if not notice:
        conn.close()
        flash("निविदा सूचना नहीं मिली।", "error")
        return redirect(url_for("tender_notices"))

    entries = db.fetchall(conn, """SELECT t.*, w.work_code, w.work_name, w.estimated_amount,
                                       w.status AS work_status, w.go_id, f.firm_name,
                                       g.go_number, g.go_date, g.govt_letter_ref, s2.scheme_name
                                FROM tenders t
                                JOIN works w ON w.work_id=t.work_id
                                LEFT JOIN go_register g ON g.go_id=w.go_id
                                LEFT JOIN schemes s2 ON s2.scheme_id=w.scheme_id
                                LEFT JOIN firms f ON f.firm_id=t.l1_firm_id
                                WHERE t.notice_id=?
                                ORDER BY g.go_id, w.work_code""", (notice_id,))

    available = db.fetchall(conn, """SELECT w.work_id, w.work_code, w.work_name, w.estimated_amount,
                                         s.scheme_name, g.go_number
                                  FROM works w
                                  LEFT JOIN schemes s ON s.scheme_id=w.scheme_id
                                  LEFT JOIN go_register g ON g.go_id=w.go_id
                                  WHERE NOT EXISTS (SELECT 1 FROM tenders t2
                                                    WHERE t2.work_id = w.work_id
                                                      AND t2.notice_id IS NOT NULL)
                                  ORDER BY g.go_number, w.work_code""")
    firms = db.fetchall(conn, "SELECT * FROM firms ORDER BY firm_name")
    schemes = db.fetchall(conn, "SELECT * FROM schemes ORDER BY scheme_name")
    accounts = db.fetchall(conn, """SELECT ba.*, s.scheme_name FROM bank_accounts ba
                                    LEFT JOIN schemes s ON s.scheme_id=ba.scheme_id
                                    ORDER BY ba.account_id""")
    gos = db.fetchall(conn, """SELECT go_id, scheme_id, go_number, go_date, govt_letter_ref
                               FROM go_register ORDER BY scheme_id, go_number""")
    conn.close()

    total_est = round(sum(float(e["estimated_amount"] or 0) for e in entries), 2)
    total_excl = round(sum(float(e["amount_excl_gst"] or 0) for e in entries), 2)
    total_emd = round(sum(float(e["emd_amount"] or 0) for e in entries), 2)
    total_l1 = round(sum(float(e["l1_amount"] or 0) for e in entries), 2)

    return render_template("tender_detail.html", notice=notice, entries=entries,
                            available=available, firms=firms, schemes=schemes, accounts=accounts,gos=gos,
                            total_est=total_est, total_excl=total_excl,
                            total_emd=total_emd, total_l1=total_l1,
                            statuses=NOTICE_STATUS_LABELS, emd_percent=int(EMD_PERCENT * 100))


@app.route("/tenders/<int:notice_id>/works/add", methods=["POST"])
@require_role("ACCOUNT_OPERATOR", "ADMIN")
def add_work_to_notice(notice_id):
    conn = db.get_db()
    notice = db.fetchone(conn, "SELECT * FROM tender_notices WHERE notice_id=?", (notice_id,))
    if not notice:
        conn.close()
        flash("निविदा सूचना नहीं मिली।", "error")
        return redirect(url_for("tender_notices"))

    duration = request.form.get("work_duration") or "3 माह"
    added = 0
    for raw in request.form.getlist("work_id"):
        try:
            work_id = int(raw)
        except (TypeError, ValueError):
            continue
        work = db.fetchone(conn, "SELECT * FROM works WHERE work_id=?", (work_id,))
        if not work:
            continue

        excl = _excl_gst(work["estimated_amount"])
        emd = _emd_amount(excl)
        fee = _tender_fee(excl)

        existing = db.fetchone(conn, """SELECT * FROM tenders WHERE work_id=? AND notice_id IS NULL
                                        ORDER BY tender_id DESC LIMIT 1""", (work_id,))
        if existing:
            db.run(conn, """UPDATE tenders SET notice_id=?, tender_no=?, tender_date=?, tender_amount=?,
                            amount_excl_gst=?, emd_amount=?, tender_fee=?, work_duration=?
                            WHERE tender_id=?""",
                   (notice_id, notice["notice_no"], notice["notice_date"], excl,
                    excl, emd, fee, duration, existing["tender_id"]))
        else:
            db.insert_and_get_id(conn, "tenders", "tender_id",
                ["work_id", "notice_id", "tender_no", "tender_date", "tender_amount",
                 "amount_excl_gst", "emd_amount", "tender_fee", "work_duration"],
                (work_id, notice_id, notice["notice_no"], notice["notice_date"], excl,
                 excl, emd, fee, duration))

        db.run(conn, "UPDATE works SET status='TENDERED' WHERE work_id=?", (work_id,))
        added += 1

    conn.commit()
    conn.close()
    if added:
        flash(f"{added} कार्य निविदा में जोड़े गए।", "success")
    else:
        flash("कोई कार्य नहीं चुना गया।", "error")
    return redirect(url_for("tender_notice_detail", notice_id=notice_id))


@app.route("/tenders/entry/<int:tender_id>/update", methods=["POST"])
@require_role("ACCOUNT_OPERATOR", "ADMIN")
def update_tender_entry(tender_id):
    conn = db.get_db()
    row = db.fetchone(conn, "SELECT * FROM tenders WHERE tender_id=?", (tender_id,))
    if not row:
        conn.close()
        flash("प्रविष्टि नहीं मिली।", "error")
        return redirect(url_for("tender_notices"))

    l1_firm_id = request.form.get("l1_firm_id")
   db.run(conn, """UPDATE tenders SET bid_no=?, amount_excl_gst=?, tender_fee=?, emd_amount=?, work_duration=?,
                       emd_verified=?, emd_bank_ref=?, l1_firm_id=?, l1_amount=?,
                       agreement_no=?, agreement_date=? WHERE tender_id=?""",
           (request.form.get("bid_no"),
            to_float(request.form.get("amount_excl_gst") or 0),
            to_float(request.form.get("tender_fee") or 0),
            to_float(request.form.get("emd_amount") or 0),
            request.form.get("work_duration"),
            bool(request.form.get("emd_verified")),
            request.form.get("emd_bank_ref"),
            int(l1_firm_id) if l1_firm_id else None,
            to_float(request.form.get("l1_amount") or 0) or None,
            request.form.get("agreement_no"),
            request.form.get("agreement_date") or None,
            tender_id))
    conn.commit()
    conn.close()
    flash("टेंडर विवरण अपडेट हुआ।", "success")
    return redirect(url_for("tender_notice_detail", notice_id=row["notice_id"]))


@app.route("/tenders/entry/<int:tender_id>/remove", methods=["POST"])
@require_role("ACCOUNT_OPERATOR", "ADMIN")
def remove_work_from_notice(tender_id):
    conn = db.get_db()
    row = db.fetchone(conn, "SELECT * FROM tenders WHERE tender_id=?", (tender_id,))
    notice_id = row["notice_id"] if row else None
    if row:
        db.run(conn, "UPDATE tenders SET notice_id=NULL WHERE tender_id=?", (tender_id,))
        conn.commit()
        flash("कार्य इस निविदा से हटा दिया गया।", "success")
    conn.close()
    return redirect(url_for("tender_notice_detail", notice_id=notice_id) if notice_id else url_for("tender_notices"))


# -----------------------------------------------------------------------------
# निविदा आमंत्रण सूचना (NIT) — प्रिंट
# -----------------------------------------------------------------------------

@app.route("/tenders/<int:notice_id>/nit")
@login_required
def tender_nit_print(notice_id):
    conn = db.get_db()
    notice = db.fetchone(conn, """SELECT n.*, s.scheme_name FROM tender_notices n
                                  LEFT JOIN schemes s ON s.scheme_id=n.scheme_id
                                  WHERE n.notice_id=?""", (notice_id,))
    if not notice:
        conn.close()
        flash("निविदा सूचना नहीं मिली।", "error")
        return redirect(url_for("tender_notices"))

    entries = db.fetchall(conn, """SELECT t.*, w.work_name, w.work_code, w.estimated_amount, w.go_id,
                                       g.go_number, g.go_date, g.govt_letter_ref, s2.scheme_name
                                FROM tenders t
                                JOIN works w ON w.work_id=t.work_id
                                LEFT JOIN go_register g ON g.go_id=w.go_id
                                LEFT JOIN schemes s2 ON s2.scheme_id=w.scheme_id
                                WHERE t.notice_id=?
                                ORDER BY g.go_id, w.work_code""", (notice_id,))

    account = None
    if notice["fee_bank_account_id"]:
        account = db.fetchone(conn, "SELECT * FROM bank_accounts WHERE account_id=?", (notice["fee_bank_account_id"],))
    conn.close()

    # GO-वार समूह बनाएं (क्रम बना रहे)
    groups, seen = [], {}
    for e in entries:
        key = e["go_id"]
        if key not in seen:
            seen[key] = {"scheme_name": e["scheme_name"], "govt_letter_ref": e["govt_letter_ref"],
                          "go_number": e["go_number"], "go_date": e["go_date"], "items": []}
            groups.append(seen[key])
        seen[key]["items"].append(e)

    letter_refs = [g["govt_letter_ref"] for g in groups if g["govt_letter_ref"]]
    scheme_names = []
    for g in groups:
        if g["scheme_name"] and g["scheme_name"] not in scheme_names:
            scheme_names.append(g["scheme_name"])

    return render_template("tender_nit.html", notice=notice, groups=groups, account=account,
                            letter_refs=letter_refs, scheme_names=scheme_names,
                            emd_percent=int(EMD_PERCENT * 100), total_works=len(entries))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
