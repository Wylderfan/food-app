import math
from itertools import zip_longest

from flask import Blueprint, jsonify, request, render_template, redirect, url_for, flash, current_app
from app import db
from app.models import Ingredient, Recipe, RecipeIngredient, DailyLogEntry
from app.utils.helpers import _float
from app.utils.macros import calculate_recipe_macros

recipes_bp = Blueprint("recipes", __name__)


# ── UI ────────────────────────────────────────────────────────────────────────

@recipes_bp.route("/recipes")
def list_recipes():
    recipes = Recipe.query.order_by(Recipe.name).all()
    if not current_app.config["ENABLE_NUTRITION"]:
        return render_template("recipes/list.html", recipes=recipes)
    macro_data = {}
    for r in recipes:
        try:
            _, ps = calculate_recipe_macros(r)
        except ValueError:
            ps = dict(calories=0, protein=0, carbs=0, fat=0, fiber=0, sugar=0)
        macro_data[r.id] = ps
    return render_template("recipes/list.html", recipes=recipes, macro_data=macro_data)


@recipes_bp.route("/recipes/<int:id>")
def view_recipe(id):
    recipe = Recipe.query.get_or_404(id)
    if not current_app.config["ENABLE_NUTRITION"]:
        return render_template("recipes/detail.html", recipe=recipe)
    try:
        total, per_serving = calculate_recipe_macros(recipe)
    except ValueError as e:
        total = per_serving = dict(calories=0, protein=0, carbs=0, fat=0, fiber=0, sugar=0)
        flash(str(e), "error")
    return render_template("recipes/detail.html", recipe=recipe, total=total, per_serving=per_serving)


@recipes_bp.route("/recipes/new", methods=["GET", "POST"])
def new_recipe():
    if request.method == "POST":
        items = _parse_form_items(request.form)
        errors = _validate_recipe_form(request.form)
        errors.update(_validate_items(items))
        if errors:
            return render_template("recipes/form.html", errors=errors, recipe=None,
                                   form=request.form, initial_items=items,
                                   **_form_context(exclude_id=None))
        recipe = Recipe(
            name=request.form["name"].strip(),
            description=request.form.get("description", "").strip() or None,
            total_servings=_float(request.form["total_servings"]),
            instructions=request.form.get("instructions", "").strip() or None,
        )
        db.session.add(recipe)
        db.session.flush()
        _replace_recipe_items(recipe.id, items)
        db.session.commit()
        flash(f"'{recipe.name}' created.", "success")
        return redirect(url_for("recipes.view_recipe", id=recipe.id))
    return render_template("recipes/form.html", errors={}, recipe=None,
                           form={}, initial_items=[],
                           **_form_context(exclude_id=None))


@recipes_bp.route("/recipes/<int:id>/edit", methods=["GET", "POST"])
def edit_recipe(id):
    recipe = Recipe.query.get_or_404(id)
    if request.method == "POST":
        items = _parse_form_items(request.form)
        errors = _validate_recipe_form(request.form)
        errors.update(_validate_items(items, id))
        if errors:
            return render_template("recipes/form.html", errors=errors, recipe=recipe,
                                   form=request.form, initial_items=items,
                                   **_form_context(exclude_id=id))
        recipe.name = request.form["name"].strip()
        recipe.description = request.form.get("description", "").strip() or None
        recipe.total_servings = _float(request.form["total_servings"])
        recipe.instructions = request.form.get("instructions", "").strip() or None
        _replace_recipe_items(recipe.id, items)
        db.session.commit()
        flash(f"'{recipe.name}' updated.", "success")
        return redirect(url_for("recipes.view_recipe", id=recipe.id))
    initial_items = _recipe_items_for_form(recipe)
    return render_template("recipes/form.html", errors={}, recipe=recipe,
                           form={}, initial_items=initial_items,
                           **_form_context(exclude_id=id))


# NOTE: PROJECT.md 2.3 — delete confirmation should preview affected recipes
# before submission, not surface the conflict only after a failed POST. Replace
# the JS confirm() with a server-rendered confirm page that lists the parents.
@recipes_bp.route("/recipes/<int:id>/delete", methods=["POST"])
def delete_recipe(id):
    recipe = Recipe.query.get_or_404(id)
    used_in = RecipeIngredient.query.filter_by(sub_recipe_id=id).first()
    if used_in:
        parent = Recipe.query.get(used_in.recipe_id)
        flash(f"Cannot delete — used as a sub-recipe in '{parent.name}'.", "error")
        return redirect(url_for("recipes.view_recipe", id=id))
    name = recipe.name
    log_count = DailyLogEntry.query.filter_by(recipe_id=id).count()
    if log_count:
        flash("Cannot delete a recipe with archived meal history. Keep it until history migration is available.", "error")
        return redirect(url_for("recipes.view_recipe", id=id))
    db.session.delete(recipe)
    db.session.commit()
    msg = f"'{name}' deleted."
    if log_count:
        msg += f" {log_count} log entr{'y' if log_count == 1 else 'ies'} also removed."
    flash(msg, "success")
    return redirect(url_for("recipes.list_recipes"))


# ── API ───────────────────────────────────────────────────────────────────────

@recipes_bp.route("/api/recipes", methods=["GET"])
def api_list():
    recipes = Recipe.query.order_by(Recipe.name).all()
    if not current_app.config["ENABLE_NUTRITION"]:
        return jsonify([r.to_dict() for r in recipes])
    result = []
    for r in recipes:
        macro_error = None
        try:
            _, ps = calculate_recipe_macros(r)
        except ValueError as e:
            ps = dict(calories=0, protein=0, carbs=0, fat=0, fiber=0, sugar=0)
            macro_error = str(e)
        d = r.to_dict()
        d["perServingMacros"] = ps
        if macro_error:
            d["macroError"] = macro_error
        result.append(d)
    return jsonify(result)


@recipes_bp.route("/api/recipes", methods=["POST"])
def api_create():
    data = request.get_json() or {}
    errors = _validate_recipe_data(data)
    items = _parse_api_items(data.get("ingredients", [])) if isinstance(data, dict) else []
    errors.update(_validate_items(items))
    if errors:
        return jsonify({"errors": errors}), 422
    recipe = Recipe(
        name=data["name"].strip(),
        description=(data.get("description") or "").strip() or None,
        total_servings=data["totalServings"],
        instructions=(data.get("instructions") or "").strip() or None,
    )
    db.session.add(recipe)
    db.session.flush()
    _replace_recipe_items(recipe.id, items)
    db.session.commit()
    return jsonify(_recipe_detail_dict(recipe)), 201


@recipes_bp.route("/api/recipes/<int:id>", methods=["GET"])
def api_get(id):
    recipe = Recipe.query.get_or_404(id)
    return jsonify(_recipe_detail_dict(recipe))


@recipes_bp.route("/api/recipes/<int:id>", methods=["PUT"])
def api_update(id):
    recipe = Recipe.query.get_or_404(id)
    data = request.get_json() or {}
    errors = _validate_recipe_data(data)
    items = _parse_api_items(data.get("ingredients", [])) if isinstance(data, dict) else []
    errors.update(_validate_items(items, id))
    if errors:
        return jsonify({"errors": errors}), 422
    recipe.name = data["name"].strip()
    recipe.description = (data.get("description") or "").strip() or None
    recipe.total_servings = data["totalServings"]
    recipe.instructions = (data.get("instructions") or "").strip() or None
    _replace_recipe_items(recipe.id, items)
    db.session.commit()
    return jsonify(_recipe_detail_dict(recipe))


@recipes_bp.route("/api/recipes/<int:id>", methods=["DELETE"])
def api_delete(id):
    recipe = Recipe.query.get_or_404(id)
    used_in = RecipeIngredient.query.filter_by(sub_recipe_id=id).first()
    if used_in:
        parent = Recipe.query.get(used_in.recipe_id)
        return jsonify({"error": f"Used as sub-recipe in '{parent.name}'"}), 409
    if DailyLogEntry.query.filter_by(recipe_id=id).first():
        return jsonify({"error": "Recipe has archived meal history; deletion is blocked to preserve it."}), 409
    db.session.delete(recipe)
    db.session.commit()
    return jsonify({"deleted": id})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _form_context(exclude_id):
    ingredients = Ingredient.query.order_by(Ingredient.name).all()
    recipes = Recipe.query.order_by(Recipe.name).all()

    ingredients_json = {
        str(i.id): {"name": i.name, "brand": i.brand, "servingUnit": i.serving_unit}
        for i in ingredients
    }
    recipes_json = {
        str(r.id): {"name": r.name, "totalServings": r.total_servings}
        for r in recipes if r.id != exclude_id
    }
    if current_app.config["ENABLE_NUTRITION"]:
        for i in ingredients:
            ingredients_json[str(i.id)].update(servingSize=i.serving_size,
                calories=i.calories, protein=i.protein, carbs=i.carbs, fat=i.fat)
        for r in recipes:
            if r.id == exclude_id:
                continue
            try:
                total, _ = calculate_recipe_macros(r)
            except ValueError:
                total = dict(calories=0, protein=0, carbs=0, fat=0, fiber=0, sugar=0)
            recipes_json[str(r.id)]["totalMacros"] = total
    return {"ingredients_json": ingredients_json, "recipes_json": recipes_json}


def _recipe_items_for_form(recipe):
    items = []
    for ri in recipe.recipe_ingredients:
        items.append({
            "type": "ingredient" if ri.ingredient_id else "subrecipe",
            "refId": ri.ingredient_id or ri.sub_recipe_id,
            "quantity": ri.quantity,
            "unit": ri.unit,
        })
    return items


def _parse_form_items(form):
    # Keep invalid and incomplete rows intact so validation can explain them.
    items = []
    columns = [form.getlist(key) for key in
               ("item_type", "item_ref_id", "item_quantity", "item_unit")]
    for kind, ref, quantity, unit in zip_longest(*columns, fillvalue=""):
        if not ref and not quantity and not unit:
            continue  # The untouched initial empty row is optional.
        items.append({"type": kind, "refId": ref, "quantity": quantity, "unit": unit})
    return items


def _parse_api_items(raw):
    if not isinstance(raw, list):
        return [None]
    items = []
    for item in raw:
        if not isinstance(item, dict) or bool(item.get("ingredientId")) == bool(item.get("subRecipeId")):
            items.append(None)
            continue
        kind = "ingredient" if item.get("ingredientId") else "subrecipe"
        items.append({"type": kind,
                      "refId": item.get("ingredientId") if kind == "ingredient" else item.get("subRecipeId"),
                      "quantity": item.get("quantity"), "unit": item.get("unit", "")})
    return items


def _positive_number(value):
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value)) and float(value) > 0
    except (ValueError, TypeError, OverflowError):
        return False


def _validate_items(items, recipe_id=None):
    messages = []
    for index, item in enumerate(items, 1):
        prefix = f"Row {index}: "
        if not isinstance(item, dict) or item.get("type") not in ("ingredient", "subrecipe"):
            messages.append(prefix + "choose one ingredient or sub-recipe.")
            continue
        ref = item.get("refId")
        try:
            ident = int(ref)
            if isinstance(ref, bool) or str(ident) != str(ref) or not 1 <= ident <= 2**63 - 1:
                raise ValueError
        except (ValueError, TypeError, OverflowError):
            messages.append(prefix + "choose an ingredient or sub-recipe.")
            continue
        model = Ingredient if item["type"] == "ingredient" else Recipe
        obj = db.session.get(model, ident)
        if obj is None:
            messages.append(prefix + "that ingredient or sub-recipe no longer exists; select another.")
            continue
        if not _positive_number(item.get("quantity")):
            messages.append(prefix + "quantity must be a finite number greater than 0.")
        if item["type"] == "subrecipe" and _would_cycle(ident, recipe_id):
            messages.append(prefix + "a recipe cannot contain itself, directly or through another recipe.")
        expected_unit = obj.serving_unit if item["type"] == "ingredient" else "serving"
        if item.get("unit") not in ("", None, expected_unit):
            messages.append(prefix + f"use the stock unit ({expected_unit}); unit conversion is not supported.")
    return {"items": " ".join(messages)} if messages else {}


def _would_cycle(candidate_id, recipe_id):
    def visit(ident, active):
        if ident == recipe_id or ident in active:
            return True
        children = RecipeIngredient.query.filter_by(recipe_id=ident).all()
        return any(visit(row.sub_recipe_id, active | {ident})
                   for row in children if row.sub_recipe_id is not None)
    return visit(candidate_id, set())


def _replace_recipe_items(recipe_id, items):
    RecipeIngredient.query.filter_by(recipe_id=recipe_id).delete()
    for item in items:
        ident = int(item["refId"])
        unit = (db.session.get(Ingredient, ident).serving_unit
                if item["type"] == "ingredient" else "serving")
        ri = RecipeIngredient(
            recipe_id=recipe_id,
            ingredient_id=ident if item["type"] == "ingredient" else None,
            sub_recipe_id=ident if item["type"] == "subrecipe" else None,
            quantity=float(item["quantity"]),
            unit=unit,
        )
        db.session.add(ri)


def _recipe_detail_dict(recipe):
    d = recipe.to_dict()
    if current_app.config["ENABLE_NUTRITION"]:
        try:
            total, per_serving = calculate_recipe_macros(recipe)
            d["macros"] = {"total": total, "perServing": per_serving}
        except ValueError as e:
            d["macroError"] = str(e)
    d["ingredients"] = [
        {
            "id": ri.id,
            "ingredientId": ri.ingredient_id,
            "subRecipeId": ri.sub_recipe_id,
            "name": (ri.ingredient.name if ri.ingredient else ri.sub_recipe.name) if (ri.ingredient or ri.sub_recipe) else None,
            "quantity": ri.quantity,
            "unit": ri.unit,
        }
        for ri in recipe.recipe_ingredients
    ]
    return d


def _validate_recipe_form(form):
    errors = {}
    if not form.get("name", "").strip():
        errors["name"] = "Name is required."
    servings = _float(form.get("total_servings"))
    if servings is None:
        errors["total_servings"] = "Total servings is required."
    elif not _positive_number(servings):
        errors["total_servings"] = "Total servings must be greater than 0."
    return errors


def _validate_recipe_data(data):
    errors = {}
    if not isinstance(data, dict):
        return {"form": "Expected a JSON object."}
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        errors["name"] = "Name is required."
    for field in ("description", "instructions"):
        if data.get(field) is not None and not isinstance(data[field], str):
            errors[field] = "Must be text."
    s = data.get("totalServings")
    if s is None:
        errors["totalServings"] = "Total servings is required."
    elif not isinstance(s, (int, float)) or not _positive_number(s):
        errors["totalServings"] = "Total servings must be greater than 0."
    return errors
