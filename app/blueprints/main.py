from flask import Blueprint, render_template, request, session, redirect, url_for, current_app

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    return render_template("main/index.html")


@main_bp.route("/switch-profile", methods=["POST"])
def switch_profile():
    profiles = [p.strip() for p in current_app.config["PROFILES"].split(",")]
    requested = request.form.get("profile", "")
    if requested in profiles:
        session["profile"] = requested
    return redirect(request.referrer or url_for("main.index"))
