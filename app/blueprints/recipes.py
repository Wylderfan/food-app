import json
from flask import Blueprint, jsonify, request, render_template, redirect, url_for, flash
from app import db
from app.models import Ingredient, Recipe, RecipeIngredient
from app.utils.helpers import current_profile, _float
from app.utils.macros import calculate_recipe_macros

recipes_bp = Blueprint("recipes", __name__)


# ── UI ────────────────────────────────────────────────────────────────────────

@recipes_bp.route("/recipes")
def list_recipes():
    profile = current_profile()
    recipes = Recipe.query.filter_by(profile_id=profile).order_by(Recipe.name).all()
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
    profile = current_profile()
    recipe = Recipe.query.filter_by(id=id, profile_id=profile).first_or_404()
    try:
        total, per_serving = calculate_recipe_macros(recipe)
    except ValueError as e:
        total = per_serving = dict(calories=0, protein=0, carbs=0, fat=0, fiber=0, sugar=0)
        flash(str(e), "error")
    return render_template("recipes/detail.html", recipe=recipe, total=total, per_serving=per_serving)


@recipes_bp.route("/recipes/new", methods=["GET", "POST"])
def new_recipe():
    profile = current_profile()
    if request.method == "POST":
        errors = _validate_recipe_form(request.form)
        items = _parse_form_items(request.form)
        if errors:
            return render_template("recipes/form.html", errors=errors, recipe=None,
                                   form=request.form, initial_items=items,
                                   **_form_context(profile, exclude_id=None))
        recipe = Recipe(
            profile_id=profile,
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
                           **_form_context(profile, exclude_id=None))


@recipes_bp.route("/recipes/<int:id>/edit", methods=["GET", "POST"])
def edit_recipe(id):
    profile = current_profile()
    recipe = Recipe.query.filter_by(id=id, profile_id=profile).first_or_404()
    if request.method == "POST":
        errors = _validate_recipe_form(request.form)
        items = _parse_form_items(request.form)
        if errors:
            return render_template("recipes/form.html", errors=errors, recipe=recipe,
                                   form=request.form, initial_items=items,
                                   **_form_context(profile, exclude_id=id))
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
                           **_form_context(profile, exclude_id=id))


# NOTE: PROJECT.md 2.3 — delete confirmation should preview affected recipes
# before submission, not surface the conflict only after a failed POST. Replace
# the JS confirm() with a server-rendered confirm page that lists the parents.
@recipes_bp.route("/recipes/<int:id>/delete", methods=["POST"])
def delete_recipe(id):
    profile = current_profile()
    recipe = Recipe.query.filter_by(id=id, profile_id=profile).first_or_404()
    used_in = RecipeIngredient.query.filter_by(sub_recipe_id=id).first()
    if used_in:
        parent = Recipe.query.get(used_in.recipe_id)
        flash(f"Cannot delete — used as a sub-recipe in '{parent.name}'.", "error")
        return redirect(url_for("recipes.view_recipe", id=id))
    name = recipe.name
    db.session.delete(recipe)
    db.session.commit()
    flash(f"'{name}' deleted.", "success")
    return redirect(url_for("recipes.list_recipes"))


# ── API ───────────────────────────────────────────────────────────────────────

@recipes_bp.route("/api/recipes", methods=["GET"])
def api_list():
    profile = current_profile()
    recipes = Recipe.query.filter_by(profile_id=profile).order_by(Recipe.name).all()
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
    if errors:
        return jsonify({"errors": errors}), 422
    recipe = Recipe(
        profile_id=current_profile(),
        name=data["name"].strip(),
        description=(data.get("description") or "").strip() or None,
        total_servings=data["totalServings"],
        instructions=(data.get("instructions") or "").strip() or None,
    )
    db.session.add(recipe)
    db.session.flush()
    _replace_recipe_items(recipe.id, _parse_api_items(data.get("ingredients", [])))
    db.session.commit()
    return jsonify(_recipe_detail_dict(recipe)), 201


@recipes_bp.route("/api/recipes/<int:id>", methods=["GET"])
def api_get(id):
    recipe = Recipe.query.filter_by(id=id, profile_id=current_profile()).first_or_404()
    return jsonify(_recipe_detail_dict(recipe))


@recipes_bp.route("/api/recipes/<int:id>", methods=["PUT"])
def api_update(id):
    recipe = Recipe.query.filter_by(id=id, profile_id=current_profile()).first_or_404()
    data = request.get_json() or {}
    errors = _validate_recipe_data(data)
    if errors:
        return jsonify({"errors": errors}), 422
    recipe.name = data["name"].strip()
    recipe.description = (data.get("description") or "").strip() or None
    recipe.total_servings = data["totalServings"]
    recipe.instructions = (data.get("instructions") or "").strip() or None
    _replace_recipe_items(recipe.id, _parse_api_items(data.get("ingredients", [])))
    db.session.commit()
    return jsonify(_recipe_detail_dict(recipe))


@recipes_bp.route("/api/recipes/<int:id>", methods=["DELETE"])
def api_delete(id):
    recipe = Recipe.query.filter_by(id=id, profile_id=current_profile()).first_or_404()
    used_in = RecipeIngredient.query.filter_by(sub_recipe_id=id).first()
    if used_in:
        parent = Recipe.query.get(used_in.recipe_id)
        return jsonify({"error": f"Used as sub-recipe in '{parent.name}'"}), 409
    db.session.delete(recipe)
    db.session.commit()
    return jsonify({"deleted": id})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _form_context(profile, exclude_id):
    ingredients = Ingredient.query.filter_by(profile_id=profile).order_by(Ingredient.name).all()
    recipes = Recipe.query.filter_by(profile_id=profile).order_by(Recipe.name).all()

    ingredients_json = {
        str(i.id): {
            "name": i.name,
            "brand": i.brand,
            "servingSize": i.serving_size,
            "servingUnit": i.serving_unit,
            "calories": i.calories,
            "protein": i.protein,
            "carbs": i.carbs,
            "fat": i.fat,
        }
        for i in ingredients
    }

    recipes_json = {}
    for r in recipes:
        if r.id == exclude_id:
            continue
        try:
            total, _ = calculate_recipe_macros(r)
        except ValueError:
            total = dict(calories=0, protein=0, carbs=0, fat=0, fiber=0, sugar=0)
        recipes_json[str(r.id)] = {
            "name": r.name,
            "totalServings": r.total_servings,
            "totalMacros": total,
        }

    return {
        "ingredients_json": json.dumps(ingredients_json),
        "recipes_json": json.dumps(recipes_json),
    }


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
    types = form.getlist("item_type")
    ref_ids = form.getlist("item_ref_id")
    quantities = form.getlist("item_quantity")
    units = form.getlist("item_unit")
    items = []
    for t, ref_id, qty, unit in zip(types, ref_ids, quantities, units):
        if not ref_id or not qty:
            continue
        try:
            items.append({
                "type": t,
                "refId": int(ref_id),
                "quantity": float(qty),
                "unit": unit.strip(),
            })
        except (ValueError, TypeError):
            continue
    return items


# NOTE: silently drops items missing ingredientId/subRecipeId/quantity rather
# than rejecting the request — POSTers can't tell rows were ignored. Tighten
# to return 422 with the offending indices when this is touched again.
def _parse_api_items(raw):
    items = []
    for item in raw:
        if item.get("ingredientId"):
            items.append({"type": "ingredient", "refId": item["ingredientId"],
                          "quantity": item["quantity"], "unit": item.get("unit", "g")})
        elif item.get("subRecipeId"):
            items.append({"type": "subrecipe", "refId": item["subRecipeId"],
                          "quantity": item["quantity"], "unit": item.get("unit", "serving")})
    return items


# NOTE: doesn't verify refId belongs to the current profile, so a crafted POST
# could attach another profile's ingredient/recipe. Single-profile-only today;
# becomes a real isolation gap once PROFILES has more than one entry.
def _replace_recipe_items(recipe_id, items):
    RecipeIngredient.query.filter_by(recipe_id=recipe_id).delete()
    for item in items:
        ri = RecipeIngredient(
            recipe_id=recipe_id,
            ingredient_id=item["refId"] if item["type"] == "ingredient" else None,
            sub_recipe_id=item["refId"] if item["type"] == "subrecipe" else None,
            quantity=item["quantity"],
            unit=item["unit"],
        )
        db.session.add(ri)


def _recipe_detail_dict(recipe):
    macro_error = None
    try:
        total, per_serving = calculate_recipe_macros(recipe)
    except ValueError as e:
        total = per_serving = dict(calories=0, protein=0, carbs=0, fat=0, fiber=0, sugar=0)
        macro_error = str(e)
    d = recipe.to_dict()
    d["macros"] = {"total": total, "perServing": per_serving}
    if macro_error:
        d["macroError"] = macro_error
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
    elif servings <= 0:
        errors["total_servings"] = "Total servings must be greater than 0."
    return errors


def _validate_recipe_data(data):
    errors = {}
    if not (data.get("name") or "").strip():
        errors["name"] = "Name is required."
    s = data.get("totalServings")
    if s is None:
        errors["totalServings"] = "Total servings is required."
    elif not isinstance(s, (int, float)) or s <= 0:
        errors["totalServings"] = "Total servings must be greater than 0."
    return errors
