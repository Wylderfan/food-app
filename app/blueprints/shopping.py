from flask import Blueprint, jsonify, request, render_template, redirect, url_for, flash
from app import db
from app.models import Ingredient, Recipe, ShoppingListItem
from app.utils.helpers import _float
from app.utils.shopping import add_ingredient, add_recipe, toggle_purchased

shopping_bp = Blueprint("shopping", __name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ordered_items():
    """Unpurchased first (by name), then purchased at the bottom."""
    return (
        ShoppingListItem.query
        .join(Ingredient, ShoppingListItem.ingredient_id == Ingredient.id)
        .order_by(ShoppingListItem.purchased.asc(), Ingredient.name.asc())
        .all()
    )


# ── UI ────────────────────────────────────────────────────────────────────────

@shopping_bp.route("/shopping-list")
def list_shopping():
    items = _ordered_items()
    ingredients = Ingredient.query.order_by(Ingredient.name).all()
    recipes = Recipe.query.order_by(Recipe.name).all()
    return render_template("shopping/list.html",
                           items=items, ingredients=ingredients, recipes=recipes)


@shopping_bp.route("/shopping-list/add-ingredient", methods=["POST"])
def ui_add_ingredient():
    ing_id = request.form.get("ingredient_id", type=int)
    qty = _float(request.form.get("quantity"))
    if not ing_id or qty is None or qty <= 0:
        flash("Ingredient and a positive quantity are required.", "error")
        return redirect(url_for("shopping.list_shopping"))
    item = add_ingredient(ing_id, qty)
    if not item:
        flash("Ingredient not found.", "error")
        return redirect(url_for("shopping.list_shopping"))
    db.session.commit()
    flash(f"Added {qty:g} {item.unit} of {item.ingredient.name}.", "success")
    return redirect(url_for("shopping.list_shopping"))


@shopping_bp.route("/shopping-list/add-recipe", methods=["POST"])
def ui_add_recipe():
    recipe_id = request.form.get("recipe_id", type=int)
    servings = _float(request.form.get("servings"))
    if not recipe_id or servings is None or servings <= 0:
        flash("Recipe and a positive servings count are required.", "error")
        return redirect(url_for("shopping.list_shopping"))
    recipe = Recipe.query.get(recipe_id)
    if not recipe:
        flash("Recipe not found.", "error")
        return redirect(url_for("shopping.list_shopping"))
    result = add_recipe(recipe, servings)
    if result is None:
        flash(f"'{recipe.name}' has a circular sub-recipe reference.", "error")
        return redirect(url_for("shopping.list_shopping"))
    touched, skipped = result
    db.session.commit()
    if not touched:
        flash(f"All ingredients for '{recipe.name}' are already in stock.", "success")
    else:
        flash(f"Added {len(touched)} item{'s' if len(touched) != 1 else ''} from '{recipe.name}'.", "success")
    return redirect(url_for("shopping.list_shopping"))


@shopping_bp.route("/shopping-list/<int:id>/toggle", methods=["POST"])
def ui_toggle(id):
    item = ShoppingListItem.query.get_or_404(id)
    toggle_purchased(item)
    db.session.commit()
    return redirect(url_for("shopping.list_shopping"))


@shopping_bp.route("/shopping-list/<int:id>/delete", methods=["POST"])
def ui_delete(id):
    item = ShoppingListItem.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for("shopping.list_shopping"))


@shopping_bp.route("/shopping-list/clear-purchased", methods=["POST"])
def ui_clear_purchased():
    count = ShoppingListItem.query.filter_by(purchased=True).delete()
    db.session.commit()
    flash(f"Cleared {count} purchased item{'s' if count != 1 else ''}.", "success")
    return redirect(url_for("shopping.list_shopping"))


# ── API ───────────────────────────────────────────────────────────────────────

@shopping_bp.route("/api/shopping-list", methods=["GET"])
def api_list():
    return jsonify([i.to_dict() for i in _ordered_items()])


@shopping_bp.route("/api/shopping-list/add-ingredient", methods=["POST"])
def api_add_ingredient():
    data = request.get_json() or {}
    errors = {}
    ing_id = data.get("ingredientId")
    qty = data.get("quantity")
    if not isinstance(ing_id, int):
        errors["ingredientId"] = "Required."
    if qty is None or not isinstance(qty, (int, float)) or qty <= 0:
        errors["quantity"] = "Must be a positive number."
    if errors:
        return jsonify({"errors": errors}), 422

    item = add_ingredient(ing_id, qty)
    if not item:
        return jsonify({"errors": {"ingredientId": "Ingredient not found."}}), 422
    db.session.commit()
    return jsonify(item.to_dict()), 201


@shopping_bp.route("/api/shopping-list/add-recipe", methods=["POST"])
def api_add_recipe():
    data = request.get_json() or {}
    errors = {}
    recipe_id = data.get("recipeId")
    servings = data.get("servings")
    if not isinstance(recipe_id, int):
        errors["recipeId"] = "Required."
    if servings is None or not isinstance(servings, (int, float)) or servings <= 0:
        errors["servings"] = "Must be a positive number."
    if errors:
        return jsonify({"errors": errors}), 422

    recipe = Recipe.query.get(recipe_id)
    if not recipe:
        return jsonify({"errors": {"recipeId": "Recipe not found."}}), 422

    result = add_recipe(recipe, servings)
    if result is None:
        return jsonify({"error": "Circular sub-recipe reference."}), 409
    touched, skipped = result
    db.session.commit()
    return jsonify({
        "added": [{"item": i.to_dict(), "quantity": q} for i, q in touched],
        "skipped": [{"ingredientId": ing.id, "ingredientName": ing.name, "reason": reason}
                    for ing, reason in skipped],
    }), 201


@shopping_bp.route("/api/shopping-list/<int:id>/toggle-purchased", methods=["PUT"])
def api_toggle(id):
    item = ShoppingListItem.query.get_or_404(id)
    toggle_purchased(item)
    db.session.commit()
    return jsonify(item.to_dict())


@shopping_bp.route("/api/shopping-list/<int:id>", methods=["DELETE"])
def api_delete(id):
    item = ShoppingListItem.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({"deleted": id})


@shopping_bp.route("/api/shopping-list/clear-purchased", methods=["DELETE"])
def api_clear_purchased():
    count = ShoppingListItem.query.filter_by(purchased=True).delete()
    db.session.commit()
    return jsonify({"deleted": count})
