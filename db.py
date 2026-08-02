"""
RNMS डेटाबेस लेयर — local विकास/परीक्षण में SQLite, Render पर PostgreSQL
(DATABASE_URL सेट होने पर) उपयोग करता है। इससे इस sandbox में (जहाँ pip/npm
इंस्टॉल नेटवर्क ब्लॉक है) बिना psycopg2 इंस्टॉल किए पूरा एप्लिकेशन लोकल रूप से
टेस्ट किया जा सकता है, और Render की अपनी build मशीन पर psycopg2-binary
(requirements.txt से) सामान्य रूप से इंस्टॉल होकर असली PostgreSQL से जुड़ जाएगा।
"""
import os
import sqlite3

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
IS_POSTGRES = DATABASE_URL.startswith("postgres")
SQLITE_PATH = os.environ.get("SQLITE_PATH", os.path.join(os.path.dirname(__file__), "rnms_dev.db"))

if IS_POSTGRES:
    import psycopg2
    import psycopg2.extras


def get_db():
    if IS_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
    return conn


def q(sql):
    """'?' प्लेसहोल्डर को postgres पर '%s' में बदलता है।"""
    return sql.replace("?", "%s") if IS_POSTGRES else sql


def run(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(q(sql), params)
    return cur


def fetchall(conn, sql, params=()):
    cur = run(conn, sql, params)
    rows = cur.fetchall()
    return [dict(r) for r in rows]


def fetchone(conn, sql, params=()):
    cur = run(conn, sql, params)
    row = cur.fetchone()
    return dict(row) if row else None


def insert_and_get_id(conn, table, pk_col, columns, values):
    """किसी टेबल में एक पंक्ति डालता है और नया PK लौटाता है — SQLite/Postgres दोनों पर काम करता है।"""
    placeholders = ", ".join(["?"] * len(columns))
    col_list = ", ".join(columns)
    if IS_POSTGRES:
        sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) RETURNING {pk_col}"
        cur = run(conn, sql, values)
        new_id = cur.fetchone()[pk_col]
        conn.commit()
        return new_id
    else:
        sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
        cur = run(conn, sql, values)
        conn.commit()
        return cur.lastrowid


def init_schema(conn):
    schema_file = "schema_postgres.sql" if IS_POSTGRES else "schema_sqlite.sql"
    path = os.path.join(os.path.dirname(__file__), schema_file)
    with open(path, encoding="utf-8") as f:
        sql = f.read()
    cur = conn.cursor()
    if IS_POSTGRES:
        cur.execute(sql)
    else:
        conn.executescript(sql)
    conn.commit()
