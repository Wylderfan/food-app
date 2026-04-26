from flask import Blueprint, jsonify, request, render_template, redirect, url_for, flash
from app import db
from app.models import Ingredient, RecipeIngredient
from app.utils.helpers import current_profile, _float

ingredients_bp = Blueprint("ingredients", __name__)


# ── UI ────────────────────────────────────────────────────────────────────────

@ingredients_bp.route("/ingredients")
def list_ingredients():
    search = request.args.get("search", "").strip()
    profile = current_profile()
    q = Ingredient.query.filter_by(profile_id=profile)
    if search:
        q = q.filter(Ingredient.name.ilike(f"%{search}%"))
    ingredients = q.order_by(Ingredient.name).all()
    return render_template("ingredients/list.html", ingredients=ingredients, search=search)


@ingredients_bp.route("/ingredients/new", methods=["GET", "POST"])
def new_ingredient():
    if request.method == "POST":
        errors = _validate_form(request.form)
        if errors:
            return render_template("ingredients/form.html", errors=errors, ingredient=None, form=request.form)
        ing = _ingredient_from_form(request.form, profile_id=current_profile())
        db.session.add(ing)
        db.session.commit()
        flash(f"'{ing.name}' added.", "success")
        return redirect(url_for("ingredients.list_ingredients"))
    return render_template("ingredients/form.html", errors={}, ingredient=None, form={})


@ingredients_bp.route("/ingredients/<int:id>/edit", methods=["GET", "POST"])
def edit_ingredient(id):
    ing = Ingredient.query.filter_by(id=id, profile_id=current_profile()).first_or_404()
    if request.method == "POST":
        errors = _validate_form(request.form)
        if errors:
            return render_template("ingredients/form.html", errors=errors, ingredient=ing, form=request.form)
        _apply_form(ing, request.form)
        db.session.commit()
        flash(f"'{ing.name}' updated.", "success")
        return redirect(url_for("ingredients.list_ingredients"))
    return render_template("ingredients/form.html", errors={}, ingredient=ing, form={})


# NOTE: PROJECT.md 1.3 — delete confirmation should preview which recipes
# would be affected before submission, not surface the conflict only via a
# flash message after a failed POST. Replace the JS confirm() with a server
# -rendered confirm page (or modal) listing affected recipes.
@ingredients_bp.route("/ingredients/<int:id>/delete", methods=["POST"])
def delete_ingredient(id):
    ing = Ingredient.query.filter_by(id=id, profile_id=current_profile()).first_or_404()
    used_in = RecipeIngredient.query.filter_by(ingredient_id=id).first()
    if used_in:
        from app.models import Recipe
        parent = Recipe.query.get(used_in.recipe_id)
        flash(f"Cannot delete — '{ing.name}' is used in recipe '{parent.name}'.", "error")
        return redirect(url_for("ingredients.list_ingredients"))
    name = ing.name
    db.session.delete(ing)
    db.session.commit()
    flash(f"'{name}' deleted.", "success")
    return redirect(url_for("ingredients.list_ingredients"))


# ── API ───────────────────────────────────────────────────────────────────────

@ingredients_bp.route("/api/ingredients", methods=["GET"])
def api_list():
    search = request.args.get("search", "").strip()
    q = Ingredient.query.filter_by(profile_id=current_profile())
    if search:
        q = q.filter(Ingredient.name.ilike(f"%{search}%"))
    return jsonify([i.to_dict() for i in q.order_by(Ingredient.name)])


@ingredients_bp.route("/api/ingredients", methods=["POST"])
def api_create():
    data = request.get_json() or {}
    errors = _validate_data(data)
    if errors:
        return jsonify({"errors": errors}), 422
    ing = Ingredient(
        profile_id=current_profile(),
        name=data["name"].strip(),
        brand=(data.get("brand") or "").strip() or None,
        serving_size=data["servingSize"],
        serving_unit=data["servingUnit"].strip(),
        calories=data.get("calories", 0),
        protein=data.get("protein", 0),
        carbs=data.get("carbs", 0),
        fat=data.get("fat", 0),
        fiber=data.get("fiber"),
        sugar=data.get("sugar"),
    )
    db.session.add(ing)
    db.session.commit()
    return jsonify(ing.to_dict()), 201


@ingredients_bp.route("/api/ingredients/<int:id>", methods=["GET"])
def api_get(id):
    ing = Ingredient.query.filter_by(id=id, profile_id=current_profile()).first_or_404()
    return jsonify(ing.to_dict())


@ingredients_bp.route("/api/ingredients/<int:id>", methods=["PUT"])
def api_update(id):
    ing = Ingredient.query.filter_by(id=id, profile_id=current_profile()).first_or_404()
    data = request.get_json() or {}
    errors = _validate_data(data)
    if errors:
        return jsonify({"errors": errors}), 422
    ing.name = data["name"].strip()
    ing.brand = (data.get("brand") or "").strip() or None
    ing.serving_size = data["servingSize"]
    ing.serving_unit = data["servingUnit"].strip()
    ing.calories = data.get("calories", 0)
    ing.protein = data.get("protein", 0)
    ing.carbs = data.get("carbs", 0)
    ing.fat = data.get("fat", 0)
    ing.fiber = data.get("fiber")
    ing.sugar = data.get("sugar")
    db.session.commit()
    return jsonify(ing.to_dict())


@ingredients_bp.route("/api/ingredients/<int:id>", methods=["DELETE"])
def api_delete(id):
    ing = Ingredient.query.filter_by(id=id, profile_id=current_profile()).first_or_404()
    used_in = RecipeIngredient.query.filter_by(ingredient_id=id).first()
    if used_in:
        from app.models import Recipe
        parent = Recipe.query.get(used_in.recipe_id)
        return jsonify({"error": f"Used in recipe '{parent.name}'"}), 409
    db.session.delete(ing)
    db.session.commit()
    return jsonify({"deleted": id})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validate_form(form):
    errors = {}
    if not form.get("name", "").strip():
        errors["name"] = "Name is required."
    size = _float(form.get("serving_size"))
    if size is None:
        errors["serving_size"] = "Serving size is required."
    elif size <= 0:
        errors["serving_size"] = "Serving size must be greater than 0."
    if not form.get("serving_unit", "").strip():
        errors["serving_unit"] = "Serving unit is required."
    for field in ["calories", "protein", "carbs", "fat", "fiber", "sugar"]:
        val = _float(form.get(field))
        if val is not None and val < 0:
            errors[field] = "Cannot be negative."
    return errors


def _validate_data(data):
    errors = {}
    if not (data.get("name") or "").strip():
        errors["name"] = "Name is required."
    size = data.get("servingSize")
    if size is None:
        errors["servingSize"] = "Serving size is required."
    elif not isinstance(size, (int, float)) or size <= 0:
        errors["servingSize"] = "Serving size must be greater than 0."
    if not (data.get("servingUnit") or "").strip():
        errors["servingUnit"] = "Serving unit is required."
    for field in ["calories", "protein", "carbs", "fat", "fiber", "sugar"]:
        val = data.get(field)
        if val is not None and (not isinstance(val, (int, float)) or val < 0):
            errors[field] = "Cannot be negative."
    return errors


def _ingredient_from_form(form, profile_id):
    return Ingredient(
        profile_id=profile_id,
        name=form["name"].strip(),
        brand=form.get("brand", "").strip() or None,
        serving_size=_float(form["serving_size"]),
        serving_unit=form["serving_unit"].strip(),
        calories=_float(form.get("calories")) or 0,
        protein=_float(form.get("protein")) or 0,
        carbs=_float(form.get("carbs")) or 0,
        fat=_float(form.get("fat")) or 0,
        fiber=_float(form.get("fiber")) if form.get("fiber") else None,
        sugar=_float(form.get("sugar")) if form.get("sugar") else None,
    )


def _apply_form(ing, form):
    ing.name = form["name"].strip()
    ing.brand = form.get("brand", "").strip() or None
    ing.serving_size = _float(form["serving_size"])
    ing.serving_unit = form["serving_unit"].strip()
    ing.calories = _float(form.get("calories")) or 0
    ing.protein = _float(form.get("protein")) or 0
    ing.carbs = _float(form.get("carbs")) or 0
    ing.fat = _float(form.get("fat")) or 0
    ing.fiber = _float(form.get("fiber")) if form.get("fiber") else None
    ing.sugar = _float(form.get("sugar")) if form.get("sugar") else None
