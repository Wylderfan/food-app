from flask import Blueprint, request, session, redirect, url_for, current_app, render_template

main_bp = Blueprint("main", __name__)


@main_bp.route("/switch-profile", methods=["POST"])
def switch_profile():
    profiles = [p.strip() for p in current_app.config["PROFILES"].split(",")]
    requested = request.form.get("profile", "")
    if requested in profiles:
        session["profile"] = requested
    return redirect(request.referrer or url_for("main.index"))


@main_bp.route("/")
def index():
    from app.models import Ingredient, InventoryItem, Recipe, ShoppingListItem
    return render_template("main/index.html",
        ingredient_count=Ingredient.query.count(),
        recipe_count=Recipe.query.count(),
        stocked_count=InventoryItem.query.filter(InventoryItem.quantity_on_hand > 0).count(),
        shopping_count=ShoppingListItem.query.filter_by(purchased=False).count())
