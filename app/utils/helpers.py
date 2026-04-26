from flask import session, current_app


def current_profile():
    profiles = [p.strip() for p in current_app.config["PROFILES"].split(",")]
    return session.get("profile", profiles[0])


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
