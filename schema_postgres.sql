-- RNMS MVP schema — PostgreSQL (Render production)
-- यह RNMS_Database_Schema.sql (पूर्ण 37-टेबल डिज़ाइन) का व्यावहारिक उपसमुच्चय है।
-- पूरी डिज़ाइन (DMS, BM-15, Closing, Security Deposit आदि) बाद के चरण में इसी पर जोड़ी जा सकती है।

CREATE TABLE IF NOT EXISTS roles (
    role_id     SERIAL PRIMARY KEY,
    role_code   VARCHAR(30) NOT NULL UNIQUE,
    role_name   VARCHAR(100) NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS users (
    user_id       SERIAL PRIMARY KEY,
    username      VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name     VARCHAR(150) NOT NULL,
    role_id       INT NOT NULL REFERENCES roles(role_id),
    email         VARCHAR(150),
    phone         VARCHAR(15),
    status        VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at    TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS schemes (
    scheme_id           SERIAL PRIMARY KEY,
    scheme_code         VARCHAR(30) NOT NULL UNIQUE,
    scheme_name         VARCHAR(200) NOT NULL,
    scheme_category     VARCHAR(30) NOT NULL,
    interest_usable     BOOLEAN NOT NULL DEFAULT FALSE,
    non_tender_allowed  BOOLEAN NOT NULL DEFAULT FALSE,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS wards (
    ward_id   SERIAL PRIMARY KEY,
    ward_no   VARCHAR(10) NOT NULL UNIQUE,
    ward_name VARCHAR(150)
);

CREATE TABLE IF NOT EXISTS financial_years (
    fy_id      SERIAL PRIMARY KEY,
    fy_name    VARCHAR(20) NOT NULL UNIQUE,
    start_date DATE NOT NULL,
    end_date   DATE NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS asset_types (
    asset_type_id   SERIAL PRIMARY KEY,
    asset_type_name VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS firms (
    firm_id         SERIAL PRIMARY KEY,
    firm_name       VARCHAR(200) NOT NULL,
    proprietor_name VARCHAR(150),
    gst_no          VARCHAR(20),
    pan_no          VARCHAR(15),
    contact_no      VARCHAR(15),
    email           VARCHAR(150),
    bank_account_no VARCHAR(30),
    bank_ifsc       VARCHAR(15),
    bank_name       VARCHAR(150),
    status          VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at      TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bank_accounts (
    account_id   SERIAL PRIMARY KEY,
    account_no   VARCHAR(30) NOT NULL UNIQUE,
    bank_name    VARCHAR(150) NOT NULL,
    branch_name  VARCHAR(150),
    ifsc_code    VARCHAR(15),
    scheme_id    INT REFERENCES schemes(scheme_id),
    opening_date DATE,
    is_active    BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS opening_balances (
    opening_balance_id SERIAL PRIMARY KEY,
    scheme_id          INT NOT NULL REFERENCES schemes(scheme_id),
    fy_id              INT NOT NULL REFERENCES financial_years(fy_id),
    amount             NUMERIC(16,2) NOT NULL DEFAULT 0,
    remarks            TEXT,
    created_by         INT REFERENCES users(user_id),
    created_at         TIMESTAMP DEFAULT now(),
    UNIQUE (scheme_id, fy_id)
);

CREATE TABLE IF NOT EXISTS go_register (
    go_id                   SERIAL PRIMARY KEY,
    scheme_id               INT NOT NULL REFERENCES schemes(scheme_id),
    fy_id                   INT REFERENCES financial_years(fy_id),
    go_number               VARCHAR(50) NOT NULL,
    go_date                 DATE NOT NULL,
    subject                 VARCHAR(300),
    total_sanctioned_amount NUMERIC(16,2) NOT NULL,
    remarks                 TEXT,
    created_by              INT REFERENCES users(user_id),
    created_at              TIMESTAMP DEFAULT now(),
    UNIQUE (scheme_id, go_number)
);

CREATE TABLE IF NOT EXISTS installments (
    installment_id    SERIAL PRIMARY KEY,
    go_id             INT NOT NULL REFERENCES go_register(go_id),
    scheme_id         INT NOT NULL REFERENCES schemes(scheme_id),
    installment_no    INT NOT NULL,
    amount_received   NUMERIC(16,2) NOT NULL,
    received_date     DATE NOT NULL,
    bank_account_id   INT REFERENCES bank_accounts(account_id),
    bank_reference_no VARCHAR(50),
    remarks           TEXT,
    created_by        INT REFERENCES users(user_id),
    created_at        TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bank_interest (
    interest_id     SERIAL PRIMARY KEY,
    bank_account_id INT NOT NULL REFERENCES bank_accounts(account_id),
    scheme_id       INT NOT NULL REFERENCES schemes(scheme_id),
    amount          NUMERIC(16,2) NOT NULL,
    credit_date     DATE NOT NULL,
    is_usable       BOOLEAN NOT NULL DEFAULT FALSE,
    remarks         TEXT,
    created_by      INT REFERENCES users(user_id),
    created_at      TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bank_charges (
    charge_id       SERIAL PRIMARY KEY,
    bank_account_id INT NOT NULL REFERENCES bank_accounts(account_id),
    scheme_id       INT NOT NULL REFERENCES schemes(scheme_id),
    txn_type        VARCHAR(20) NOT NULL,
    amount          NUMERIC(16,2) NOT NULL,
    txn_date        DATE NOT NULL,
    remarks         TEXT,
    created_by      INT REFERENCES users(user_id),
    created_at      TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS works (
    work_id           SERIAL PRIMARY KEY,
    work_code         VARCHAR(40) NOT NULL UNIQUE,
    scheme_id         INT NOT NULL REFERENCES schemes(scheme_id),
    ward_id           INT REFERENCES wards(ward_id),
    fy_id             INT NOT NULL REFERENCES financial_years(fy_id),
    asset_type_id     INT REFERENCES asset_types(asset_type_id),
    work_name         VARCHAR(300) NOT NULL,
    work_source       VARCHAR(20) NOT NULL DEFAULT 'NEW',
    is_tendered       BOOLEAN NOT NULL DEFAULT TRUE,
    estimated_amount  NUMERIC(16,2) NOT NULL,
    status            VARCHAR(30) NOT NULL DEFAULT 'PROPOSED',
    proposed_date     DATE,
    created_by        INT REFERENCES users(user_id),
    created_at        TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tenders (
    tender_id     SERIAL PRIMARY KEY,
    work_id       INT NOT NULL REFERENCES works(work_id),
    tender_no     VARCHAR(50) NOT NULL UNIQUE,
    tender_date   DATE NOT NULL,
    tender_amount NUMERIC(16,2) NOT NULL,
    l1_firm_id    INT REFERENCES firms(firm_id),
    l1_amount     NUMERIC(16,2),
    status        VARCHAR(20) NOT NULL DEFAULT 'PUBLISHED',
    remarks       TEXT,
    created_by    INT REFERENCES users(user_id),
    created_at    TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS work_orders (
    wo_id       SERIAL PRIMARY KEY,
    work_id     INT NOT NULL REFERENCES works(work_id),
    tender_id   INT REFERENCES tenders(tender_id),
    firm_id     INT NOT NULL REFERENCES firms(firm_id),
    wo_number   VARCHAR(50) NOT NULL UNIQUE,
    wo_date     DATE NOT NULL,
    wo_amount   NUMERIC(16,2) NOT NULL,
    created_by  INT REFERENCES users(user_id),
    created_at  TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bills (
    bill_id          SERIAL PRIMARY KEY,
    work_id          INT NOT NULL REFERENCES works(work_id),
    firm_id          INT NOT NULL REFERENCES firms(firm_id),
    bill_no          VARCHAR(50) NOT NULL,
    bill_date        DATE NOT NULL,
    bill_sequence_no INT NOT NULL,
    amount_excl_gst  NUMERIC(16,2) NOT NULL,
    gst_rate         NUMERIC(5,2) NOT NULL DEFAULT 0,
    gst_amount       NUMERIC(16,2) NOT NULL DEFAULT 0,
    amount_incl_gst  NUMERIC(16,2) NOT NULL,
    status           VARCHAR(20) NOT NULL DEFAULT 'SUBMITTED',
    created_by       INT REFERENCES users(user_id),
    created_at       TIMESTAMP DEFAULT now(),
    UNIQUE (work_id, bill_sequence_no)
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id                SERIAL PRIMARY KEY,
    bill_id                   INT NOT NULL REFERENCES bills(bill_id),
    work_id                   INT NOT NULL REFERENCES works(work_id),
    gross_amount              NUMERIC(16,2) NOT NULL,
    cgst_1pct                 NUMERIC(16,2) NOT NULL DEFAULT 0,
    sgst_1pct                 NUMERIC(16,2) NOT NULL DEFAULT 0,
    income_tax_2pct           NUMERIC(16,2) NOT NULL DEFAULT 0,
    labour_cess_1pct          NUMERIC(16,2) NOT NULL DEFAULT 0,
    no_deduction              BOOLEAN NOT NULL DEFAULT FALSE,
    total_deduction           NUMERIC(16,2) NOT NULL DEFAULT 0,
    net_payment               NUMERIC(16,2) NOT NULL,
    balance_against_sanction  NUMERIC(16,2),
    balance_against_l1        NUMERIC(16,2),
    ppa_no                    VARCHAR(50),
    ppa_date                  DATE,
    status                    VARCHAR(20) NOT NULL DEFAULT 'ENTERED',
    entered_by                INT NOT NULL REFERENCES users(user_id),
    entered_at                TIMESTAMP DEFAULT now(),
    verified_by               INT REFERENCES users(user_id),
    verified_at               TIMESTAMP,
    approved_by               INT REFERENCES users(user_id),
    approved_at               TIMESTAMP,
    posted_by                 INT REFERENCES users(user_id),
    posted_at                 TIMESTAMP,
    remarks                   TEXT
);

CREATE TABLE IF NOT EXISTS payment_approval_log (
    log_id        BIGSERIAL PRIMARY KEY,
    payment_id    INT NOT NULL REFERENCES payments(payment_id),
    action        VARCHAR(20) NOT NULL,
    actor_user_id INT NOT NULL REFERENCES users(user_id),
    action_at     TIMESTAMP DEFAULT now(),
    remarks       TEXT
);

CREATE TABLE IF NOT EXISTS cashbook_entries (
    entry_id        BIGSERIAL PRIMARY KEY,
    bank_account_id INT NOT NULL REFERENCES bank_accounts(account_id),
    scheme_id       INT NOT NULL REFERENCES schemes(scheme_id),
    entry_date      DATE NOT NULL,
    particulars     VARCHAR(300) NOT NULL,
    receipt_amount  NUMERIC(16,2) NOT NULL DEFAULT 0,
    payment_amount  NUMERIC(16,2) NOT NULL DEFAULT 0,
    running_balance NUMERIC(16,2) NOT NULL,
    reference_type  VARCHAR(30),
    reference_id    BIGINT,
    created_by      INT REFERENCES users(user_id),
    created_at      TIMESTAMP DEFAULT now()
);
