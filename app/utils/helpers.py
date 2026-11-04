import math
from flask import session, current_app


def current_profile():
    profiles = [p.strip() for p in current_app.config["PROFILES"].split(",")]
    return session.get("profile", profiles[0])


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _float(value):
    try:
        if isinstance(value, bool):
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def is_finite_number(value):
    return type(value) in (int, float) and _float(value) is not None
