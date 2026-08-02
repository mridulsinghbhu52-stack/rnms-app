-- RNMS MVP schema — SQLite (लोकल विकास/परीक्षण हेतु)
-- यह RNMS_Database_Schema.sql (पूर्ण 37-टेबल डिज़ाइन) का एक व्यावहारिक उपसमुच्चय है,
-- जो मुख्य प्रवाह को कवर करता है: मद/GO -> आय/किस्त -> कार्य -> टेंडर/वर्क ऑर्डर ->
-- बिल -> भुगतान अनुमोदन -> कैशबुक। पूरी डिज़ाइन (DMS, BM-15, Closing, आदि) अगले चरण में।

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS roles (
    role_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    role_code   TEXT NOT NULL UNIQUE,
    role_name   TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name     TEXT NOT NULL,
    role_id       INTEGER NOT NULL REFERENCES roles(role_id),
    email         TEXT,
    phone         TEXT,
    status        TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS schemes (
    scheme_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    scheme_code         TEXT NOT NULL UNIQUE,
    scheme_name         TEXT NOT NULL,
    scheme_category     TEXT NOT NULL,
    interest_usable     INTEGER NOT NULL DEFAULT 0,
    non_tender_allowed  INTEGER NOT NULL DEFAULT 0,
    is_active           INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS wards (
    ward_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    ward_no   TEXT NOT NULL UNIQUE,
    ward_name TEXT
);

CREATE TABLE IF NOT EXISTS financial_years (
    fy_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    fy_name    TEXT NOT NULL UNIQUE,
    start_date TEXT NOT NULL,
    end_date   TEXT NOT NULL,
    is_current INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS asset_types (
    asset_type_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_type_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS firms (
    firm_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    firm_name       TEXT NOT NULL,
    proprietor_name TEXT,
    gst_no          TEXT,
    pan_no          TEXT,
    contact_no      TEXT,
    email           TEXT,
    bank_account_no TEXT,
    bank_ifsc       TEXT,
    bank_name       TEXT,
    status          TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bank_accounts (
    account_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    account_no   TEXT NOT NULL UNIQUE,
    bank_name    TEXT NOT NULL,
    branch_name  TEXT,
    ifsc_code    TEXT,
    scheme_id    INTEGER REFERENCES schemes(scheme_id),
    opening_date TEXT,
    is_active    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS opening_balances (
    opening_balance_id INTEGER PRIMARY KEY AUTOINCREMENT,
    scheme_id          INTEGER NOT NULL REFERENCES schemes(scheme_id),
    fy_id              INTEGER NOT NULL REFERENCES financial_years(fy_id),
    amount             NUMERIC NOT NULL DEFAULT 0,
    remarks            TEXT,
    created_by         INTEGER REFERENCES users(user_id),
    created_at         TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (scheme_id, fy_id)
);

CREATE TABLE IF NOT EXISTS go_register (
    go_id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    scheme_id               INTEGER NOT NULL REFERENCES schemes(scheme_id),
    fy_id                   INTEGER REFERENCES financial_years(fy_id),
    go_number               TEXT NOT NULL,
    go_date                 TEXT NOT NULL,
    subject                 TEXT,
    total_sanctioned_amount NUMERIC NOT NULL,
    remarks                 TEXT,
    created_by              INTEGER REFERENCES users(user_id),
    created_at              TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (scheme_id, go_number)
);

CREATE TABLE IF NOT EXISTS installments (
    installment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    go_id             INTEGER NOT NULL REFERENCES go_register(go_id),
    scheme_id         INTEGER NOT NULL REFERENCES schemes(scheme_id),
    installment_no    INTEGER NOT NULL,
    amount_received   NUMERIC NOT NULL,
    received_date     TEXT NOT NULL,
    bank_account_id   INTEGER REFERENCES bank_accounts(account_id),
    bank_reference_no TEXT,
    remarks           TEXT,
    created_by        INTEGER REFERENCES users(user_id),
    created_at        TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bank_interest (
    interest_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_account_id INTEGER NOT NULL REFERENCES bank_accounts(account_id),
    scheme_id       INTEGER NOT NULL REFERENCES schemes(scheme_id),
    amount          NUMERIC NOT NULL,
    credit_date     TEXT NOT NULL,
    is_usable       INTEGER NOT NULL DEFAULT 0,
    remarks         TEXT,
    created_by      INTEGER REFERENCES users(user_id),
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bank_charges (
    charge_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_account_id INTEGER NOT NULL REFERENCES bank_accounts(account_id),
    scheme_id       INTEGER NOT NULL REFERENCES schemes(scheme_id),
    txn_type        TEXT NOT NULL,
    amount          NUMERIC NOT NULL,
    txn_date        TEXT NOT NULL,
    remarks         TEXT,
    created_by      INTEGER REFERENCES users(user_id),
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS works (
    work_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    work_code         TEXT NOT NULL UNIQUE,
    scheme_id         INTEGER NOT NULL REFERENCES schemes(scheme_id),
    ward_id           INTEGER REFERENCES wards(ward_id),
    fy_id             INTEGER NOT NULL REFERENCES financial_years(fy_id),
    asset_type_id     INTEGER REFERENCES asset_types(asset_type_id),
    work_name         TEXT NOT NULL,
    work_source       TEXT NOT NULL DEFAULT 'NEW',
    is_tendered       INTEGER NOT NULL DEFAULT 1,
    estimated_amount  NUMERIC NOT NULL,
    status            TEXT NOT NULL DEFAULT 'PROPOSED',
    proposed_date     TEXT,
    created_by        INTEGER REFERENCES users(user_id),
    created_at        TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tenders (
    tender_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id       INTEGER NOT NULL REFERENCES works(work_id),
    tender_no     TEXT NOT NULL UNIQUE,
    tender_date   TEXT NOT NULL,
    tender_amount NUMERIC NOT NULL,
    l1_firm_id    INTEGER REFERENCES firms(firm_id),
    l1_amount     NUMERIC,
    status        TEXT NOT NULL DEFAULT 'PUBLISHED',
    remarks       TEXT,
    created_by    INTEGER REFERENCES users(user_id),
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS work_orders (
    wo_id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id               INTEGER NOT NULL REFERENCES works(work_id),
    tender_id             INTEGER REFERENCES tenders(tender_id),
    firm_id               INTEGER NOT NULL REFERENCES firms(firm_id),
    wo_number             TEXT NOT NULL UNIQUE,
    wo_date               TEXT NOT NULL,
    wo_amount             NUMERIC NOT NULL,
    created_by            INTEGER REFERENCES users(user_id),
    created_at            TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bills (
    bill_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id          INTEGER NOT NULL REFERENCES works(work_id),
    firm_id          INTEGER NOT NULL REFERENCES firms(firm_id),
    bill_no          TEXT NOT NULL,
    bill_date        TEXT NOT NULL,
    bill_sequence_no INTEGER NOT NULL,
    amount_excl_gst  NUMERIC NOT NULL,
    gst_rate         NUMERIC NOT NULL DEFAULT 0,
    gst_amount       NUMERIC NOT NULL DEFAULT 0,
    amount_incl_gst  NUMERIC NOT NULL,
    status           TEXT NOT NULL DEFAULT 'SUBMITTED',
    created_by       INTEGER REFERENCES users(user_id),
    created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (work_id, bill_sequence_no)
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id                   INTEGER NOT NULL REFERENCES bills(bill_id),
    work_id                   INTEGER NOT NULL REFERENCES works(work_id),
    gross_amount              NUMERIC NOT NULL,
    cgst_1pct                 NUMERIC NOT NULL DEFAULT 0,
    sgst_1pct                 NUMERIC NOT NULL DEFAULT 0,
    income_tax_2pct           NUMERIC NOT NULL DEFAULT 0,
    labour_cess_1pct          NUMERIC NOT NULL DEFAULT 0,
    no_deduction              INTEGER NOT NULL DEFAULT 0,
    total_deduction           NUMERIC NOT NULL DEFAULT 0,
    net_payment               NUMERIC NOT NULL,
    balance_against_sanction  NUMERIC,
    balance_against_l1        NUMERIC,
    ppa_no                    TEXT,
    ppa_date                  TEXT,
    status                    TEXT NOT NULL DEFAULT 'ENTERED',
    entered_by                INTEGER NOT NULL REFERENCES users(user_id),
    entered_at                TEXT DEFAULT CURRENT_TIMESTAMP,
    verified_by               INTEGER REFERENCES users(user_id),
    verified_at               TEXT,
    approved_by               INTEGER REFERENCES users(user_id),
    approved_at               TEXT,
    posted_by                 INTEGER REFERENCES users(user_id),
    posted_at                 TEXT,
    remarks                   TEXT
);

CREATE TABLE IF NOT EXISTS payment_approval_log (
    log_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id    INTEGER NOT NULL REFERENCES payments(payment_id),
    action        TEXT NOT NULL,
    actor_user_id INTEGER NOT NULL REFERENCES users(user_id),
    action_at     TEXT DEFAULT CURRENT_TIMESTAMP,
    remarks       TEXT
);

CREATE TABLE IF NOT EXISTS cashbook_entries (
    entry_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_account_id INTEGER NOT NULL REFERENCES bank_accounts(account_id),
    scheme_id       INTEGER NOT NULL REFERENCES schemes(scheme_id),
    entry_date      TEXT NOT NULL,
    particulars     TEXT NOT NULL,
    receipt_amount  NUMERIC NOT NULL DEFAULT 0,
    payment_amount  NUMERIC NOT NULL DEFAULT 0,
    running_balance NUMERIC NOT NULL,
    reference_type  TEXT,
    reference_id    INTEGER,
    created_by      INTEGER REFERENCES users(user_id),
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);
