from flask import Blueprint, jsonify, request, render_template, redirect, url_for, flash, current_app
from app import db
from app.models import Ingredient, RecipeIngredient
from app.utils.helpers import _float
from app.utils.inventory import get_or_create_item
from app.utils.usda import search_foods, USDAError

ingredients_bp = Blueprint("ingredients", __name__)


# ── UI ────────────────────────────────────────────────────────────────────────

@ingredients_bp.route("/ingredients")
def list_ingredients():
    search = request.args.get("search", "").strip()
    q = Ingredient.query
    if search:
        q = q.filter(Ingredient.name.ilike(f"%{search}%"))
    ingredients = q.order_by(Ingredient.name).all()
    return render_template("ingredients/list.html", ingredients=ingredients, search=search)


@ingredients_bp.route("/ingredients/new", methods=["GET", "POST"])
def new_ingredient():
    if request.method == "POST":
        errors = _validate_form(request.form)
        if errors:
            return render_template("ingredients/form.html", errors=errors, ingredient=None,
                                   form=request.form, inventory_qty=None)
        ing = _ingredient_from_form(request.form)
        db.session.add(ing)
        db.session.flush()
        qty = _float(request.form.get("quantity_on_hand"))
        if qty is not None and qty != 0:
            item = get_or_create_item(ing.id)
            item.quantity_on_hand = qty
        db.session.commit()
        flash(f"'{ing.name}' added.", "success")
        return redirect(url_for("ingredients.list_ingredients"))
    return render_template("ingredients/form.html", errors={}, ingredient=None,
                           form={}, inventory_qty=None)


@ingredients_bp.route("/ingredients/<int:id>/edit", methods=["GET", "POST"])
def edit_ingredient(id):
    ing = Ingredient.query.get_or_404(id)
    item = ing.inventory_items[0] if ing.inventory_items else None
    if request.method == "POST":
        errors = _validate_form(request.form)
        if errors:
            return render_template("ingredients/form.html", errors=errors, ingredient=ing,
                                   form=request.form,
                                   inventory_qty=item.quantity_on_hand if item else None)
        _apply_form(ing, request.form)
        qty = _float(request.form.get("quantity_on_hand"))
        if qty is not None:
            item = get_or_create_item(ing.id)
            item.quantity_on_hand = qty
        db.session.commit()
        flash(f"'{ing.name}' updated.", "success")
        return redirect(url_for("ingredients.list_ingredients"))
    return render_template("ingredients/form.html", errors={}, ingredient=ing,
                           form={},
                           inventory_qty=item.quantity_on_hand if item else None)


# NOTE: PROJECT.md 1.3 — delete confirmation should preview which recipes
# would be affected before submission, not surface the conflict only via a
# flash message after a failed POST. Replace the JS confirm() with a server
# -rendered confirm page (or modal) listing affected recipes.
@ingredients_bp.route("/ingredients/<int:id>/delete", methods=["POST"])
def delete_ingredient(id):
    ing = Ingredient.query.get_or_404(id)
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

@ingredients_bp.route("/api/ingredients/search-external", methods=["GET"])
def api_search_external():
    query = request.args.get("query", "").strip()
    if not query:
        return jsonify({"results": []})
    try:
        results = search_foods(query, current_app.config["USDA_API_KEY"])
    except USDAError as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"results": results})


@ingredients_bp.route("/api/ingredients", methods=["GET"])
def api_list():
    search = request.args.get("search", "").strip()
    q = Ingredient.query
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
        low_stock_threshold=data.get("lowStockThreshold", 0) or 0,
    )
    db.session.add(ing)
    db.session.commit()
    return jsonify(ing.to_dict()), 201


@ingredients_bp.route("/api/ingredients/<int:id>", methods=["GET"])
def api_get(id):
    ing = Ingredient.query.get_or_404(id)
    return jsonify(ing.to_dict())


@ingredients_bp.route("/api/ingredients/<int:id>", methods=["PUT"])
def api_update(id):
    ing = Ingredient.query.get_or_404(id)
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
    if "lowStockThreshold" in data:
        ing.low_stock_threshold = data.get("lowStockThreshold") or 0
    db.session.commit()
    return jsonify(ing.to_dict())


@ingredients_bp.route("/api/ingredients/<int:id>", methods=["DELETE"])
def api_delete(id):
    ing = Ingredient.query.get_or_404(id)
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
    for field in ["calories", "protein", "carbs", "fat", "fiber", "sugar", "low_stock_threshold"]:
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
    for field in ["calories", "protein", "carbs", "fat", "fiber", "sugar", "lowStockThreshold"]:
        val = data.get(field)
        if val is not None and (not isinstance(val, (int, float)) or val < 0):
            errors[field] = "Cannot be negative."
    return errors


def _ingredient_from_form(form):
    return Ingredient(
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
        low_stock_threshold=_float(form.get("low_stock_threshold")) or 0,
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
    ing.low_stock_threshold = _float(form.get("low_stock_threshold")) or 0
