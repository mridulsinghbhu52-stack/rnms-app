from functools import wraps
from flask import session, redirect, url_for, flash, request


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


def require_role(*role_codes):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("login", next=request.path))
            if session.get("role_code") not in role_codes:
                flash("इस कार्य हेतु आपके पास अधिकार नहीं है।", "error")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return wrapper
    return decorator


def to_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def fmt_amount(val):
    try:
        return f"{float(val):,.2f}"
    except (TypeError, ValueError):
        return val
