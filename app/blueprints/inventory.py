from flask import Blueprint, jsonify, request, render_template, redirect, url_for, flash
from app import db
from app.models import Ingredient, InventoryItem
from app.utils.helpers import _float
from app.utils.inventory import get_or_create_item

inventory_bp = Blueprint("inventory", __name__)


# ── UI ────────────────────────────────────────────────────────────────────────

@inventory_bp.route("/inventory")
def list_inventory():
    items = (
        InventoryItem.query
        .join(Ingredient, InventoryItem.ingredient_id == Ingredient.id)
        .order_by(Ingredient.name).all()
    )
    ingredients = Ingredient.query.order_by(Ingredient.name).all()
    return render_template("inventory/list.html", items=items, ingredients=ingredients)


@inventory_bp.route("/inventory/add", methods=["POST"])
def add_stock():
    ingredient_id = request.form.get("ingredient_id", type=int)
    qty = _float(request.form.get("quantity"))

    if not ingredient_id or qty is None or qty <= 0:
        flash("Ingredient and a positive quantity are required.", "error")
        return redirect(url_for("inventory.list_inventory"))

    ing = Ingredient.query.get(ingredient_id)
    if not ing:
        flash("Ingredient not found.", "error")
        return redirect(url_for("inventory.list_inventory"))

    item = get_or_create_item(ingredient_id)
    item.quantity_on_hand += qty
    db.session.commit()
    flash(f"Added {qty:g} {ing.serving_unit} to '{ing.name}'.", "success")
    return redirect(url_for("inventory.list_inventory"))


# ── API ───────────────────────────────────────────────────────────────────────

@inventory_bp.route("/api/inventory", methods=["GET"])
def api_list():
    items = (
        InventoryItem.query
        .join(Ingredient, InventoryItem.ingredient_id == Ingredient.id)
        .order_by(Ingredient.name).all()
    )
    return jsonify([i.to_dict() for i in items])


@inventory_bp.route("/api/inventory/<int:ingredient_id>", methods=["PUT"])
def api_set(ingredient_id):
    ing = Ingredient.query.get_or_404(ingredient_id)
    data = request.get_json() or {}

    errors = {}
    qty = data.get("quantityOnHand")
    threshold = data.get("lowStockThreshold")

    if qty is not None and not isinstance(qty, (int, float)):
        errors["quantityOnHand"] = "Must be a number."
    if threshold is not None and (not isinstance(threshold, (int, float)) or threshold < 0):
        errors["lowStockThreshold"] = "Must be a non-negative number."
    if qty is None and threshold is None:
        errors["_"] = "Provide quantityOnHand and/or lowStockThreshold."

    if errors:
        return jsonify({"errors": errors}), 422

    item = get_or_create_item(ingredient_id)
    if qty is not None:
        item.quantity_on_hand = qty
    if threshold is not None:
        ing.low_stock_threshold = threshold
    db.session.commit()
    return jsonify(item.to_dict())


@inventory_bp.route("/api/inventory/add", methods=["POST"])
def api_add():
    data = request.get_json() or {}

    errors = {}
    ingredient_id = data.get("ingredientId")
    qty = data.get("quantity")

    if not isinstance(ingredient_id, int):
        errors["ingredientId"] = "Required."
    if qty is None or not isinstance(qty, (int, float)) or qty <= 0:
        errors["quantity"] = "Must be a positive number."

    if errors:
        return jsonify({"errors": errors}), 422

    ing = Ingredient.query.get(ingredient_id)
    if not ing:
        return jsonify({"errors": {"ingredientId": "Ingredient not found."}}), 422

    item = get_or_create_item(ingredient_id)
    item.quantity_on_hand += qty
    db.session.commit()
    return jsonify(item.to_dict())
