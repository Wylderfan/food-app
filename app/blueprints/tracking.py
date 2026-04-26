from datetime import date, datetime, timedelta
from flask import Blueprint, jsonify, request, render_template, redirect, url_for, flash
from app import db
from app.models import Recipe, DailyLogEntry, UserGoals
from app.utils.helpers import current_profile, _float
from app.utils.macros import calculate_recipe_macros
from app.utils.inventory import apply_recipe_to_inventory

tracking_bp = Blueprint("tracking", __name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _zero_macros():
    return dict(calories=0.0, protein=0.0, carbs=0.0, fat=0.0, fiber=0.0, sugar=0.0)


def _get_or_create_goals(profile_id):
    goals = UserGoals.query.filter_by(profile_id=profile_id).first()
    if not goals:
        goals = UserGoals(profile_id=profile_id)
        db.session.add(goals)
        db.session.commit()
    return goals


def _entry_macros(entry):
    if not entry.recipe:
        return _zero_macros()
    try:
        _, per_serving = calculate_recipe_macros(entry.recipe)
    except ValueError:
        return _zero_macros()
    return {k: v * entry.servings for k, v in per_serving.items()}


def _parse_date_loose(s, fallback=None):
    if not s:
        return fallback or date.today()
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return fallback or date.today()


# ── UI ────────────────────────────────────────────────────────────────────────

@tracking_bp.route("/")
def daily_log():
    profile = current_profile()
    sel_date = _parse_date_loose(request.args.get("date"))

    entries = DailyLogEntry.query.filter_by(
        profile_id=profile, date=sel_date
    ).order_by(DailyLogEntry.logged_at).all()

    items = []
    totals = _zero_macros()
    for e in entries:
        m = _entry_macros(e)
        items.append({"entry": e, "macros": m})
        for k in totals:
            totals[k] += m[k]

    goals = _get_or_create_goals(profile)
    recipes = Recipe.query.order_by(Recipe.name).all()

    return render_template(
        "tracking/daily.html",
        sel_date=sel_date,
        prev_date=sel_date - timedelta(days=1),
        next_date=sel_date + timedelta(days=1),
        today=date.today(),
        items=items,
        totals=totals,
        goals=goals,
        recipes=recipes,
    )


@tracking_bp.route("/log", methods=["POST"])
def log_meal():
    profile = current_profile()
    sel_date = _parse_date_loose(request.form.get("date"))
    recipe_id = request.form.get("recipe_id", type=int)
    servings = _float(request.form.get("servings"))

    if not recipe_id or not servings or servings <= 0:
        flash("Recipe and a positive servings count are required.", "error")
        return redirect(url_for("tracking.daily_log", date=sel_date.isoformat()))

    recipe = Recipe.query.get(recipe_id)
    if not recipe:
        flash("Recipe not found.", "error")
        return redirect(url_for("tracking.daily_log", date=sel_date.isoformat()))

    entry = DailyLogEntry(
        profile_id=profile, date=sel_date,
        recipe_id=recipe_id, servings=servings,
    )
    db.session.add(entry)
    apply_recipe_to_inventory(recipe, servings, deduct=True)
    db.session.commit()
    flash(f"Logged {servings:g} × {recipe.name}.", "success")
    return redirect(url_for("tracking.daily_log", date=sel_date.isoformat()))


@tracking_bp.route("/log/<int:id>/delete", methods=["POST"])
def delete_log(id):
    profile = current_profile()
    entry = DailyLogEntry.query.filter_by(id=id, profile_id=profile).first_or_404()
    sel_date = entry.date
    if entry.recipe:
        apply_recipe_to_inventory(entry.recipe, entry.servings, deduct=False)
    db.session.delete(entry)
    db.session.commit()
    flash("Log entry removed.", "success")
    return redirect(url_for("tracking.daily_log", date=sel_date.isoformat()))


@tracking_bp.route("/goals", methods=["GET", "POST"])
def goals_page():
    profile = current_profile()
    goals = _get_or_create_goals(profile)
    if request.method == "POST":
        errors = {}
        values = {}
        for form_key in ["daily_calories", "daily_protein", "daily_carbs", "daily_fat"]:
            v = _float(request.form.get(form_key))
            if v is None:
                errors[form_key] = "Required."
            elif v < 0:
                errors[form_key] = "Cannot be negative."
            else:
                values[form_key] = v
        if errors:
            return render_template("tracking/goals.html", goals=goals,
                                   errors=errors, form=request.form)
        for k, v in values.items():
            setattr(goals, k, v)
        db.session.commit()
        flash("Goals updated.", "success")
        return redirect(url_for("tracking.goals_page"))
    return render_template("tracking/goals.html", goals=goals, errors={}, form={})


# ── API ───────────────────────────────────────────────────────────────────────

@tracking_bp.route("/api/log", methods=["GET"])
def api_get_log():
    profile = current_profile()
    sel_date = _parse_date_loose(request.args.get("date"))
    entries = DailyLogEntry.query.filter_by(
        profile_id=profile, date=sel_date
    ).order_by(DailyLogEntry.logged_at).all()

    result = []
    totals = _zero_macros()
    for e in entries:
        m = _entry_macros(e)
        result.append(e.to_dict(macros=m))
        for k in totals:
            totals[k] += m[k]

    return jsonify({"date": sel_date.isoformat(), "entries": result, "totals": totals})


@tracking_bp.route("/api/log", methods=["POST"])
def api_log_meal():
    profile = current_profile()
    data = request.get_json() or {}

    errors = {}
    recipe_id = data.get("recipeId")
    servings = data.get("servings")
    date_str = data.get("date")

    if not isinstance(recipe_id, int):
        errors["recipeId"] = "Recipe ID is required."
    if servings is None or not isinstance(servings, (int, float)) or servings <= 0:
        errors["servings"] = "Servings must be a positive number."

    sel_date = date.today()
    if date_str:
        try:
            sel_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            errors["date"] = "Date must be YYYY-MM-DD."

    if errors:
        return jsonify({"errors": errors}), 422

    recipe = Recipe.query.get(recipe_id)
    if not recipe:
        return jsonify({"errors": {"recipeId": "Recipe not found."}}), 422

    entry = DailyLogEntry(
        profile_id=profile, date=sel_date,
        recipe_id=recipe_id, servings=servings,
    )
    db.session.add(entry)
    apply_recipe_to_inventory(recipe, servings, deduct=True)
    db.session.commit()
    return jsonify(entry.to_dict(macros=_entry_macros(entry))), 201


@tracking_bp.route("/api/log/<int:id>", methods=["DELETE"])
def api_delete_log(id):
    profile = current_profile()
    entry = DailyLogEntry.query.filter_by(id=id, profile_id=profile).first_or_404()
    if entry.recipe:
        apply_recipe_to_inventory(entry.recipe, entry.servings, deduct=False)
    db.session.delete(entry)
    db.session.commit()
    return jsonify({"deleted": id})


@tracking_bp.route("/api/goals", methods=["GET"])
def api_get_goals():
    return jsonify(_get_or_create_goals(current_profile()).to_dict())


@tracking_bp.route("/api/goals", methods=["PUT"])
def api_set_goals():
    goals = _get_or_create_goals(current_profile())
    data = request.get_json() or {}

    field_map = {
        "dailyCalories": "daily_calories",
        "dailyProtein": "daily_protein",
        "dailyCarbs": "daily_carbs",
        "dailyFat": "daily_fat",
    }

    errors = {}
    for json_key in field_map:
        if json_key in data:
            v = data[json_key]
            if not isinstance(v, (int, float)) or v < 0:
                errors[json_key] = "Must be a non-negative number."
    if errors:
        return jsonify({"errors": errors}), 422

    for json_key, attr in field_map.items():
        if json_key in data:
            setattr(goals, attr, data[json_key])
    db.session.commit()
    return jsonify(goals.to_dict())
