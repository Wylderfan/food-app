from app import db
from app.models import Ingredient, InventoryItem, ShoppingListItem
from app.utils.inventory import flatten_recipe, get_or_create_item


def _existing_unpurchased(ingredient_id):
    return ShoppingListItem.query.filter_by(
        ingredient_id=ingredient_id, purchased=False
    ).first()


def add_ingredient(ingredient_id, quantity, source="manual"):
    """
    Manual add. No inventory check. Increments existing unpurchased entry
    if any, otherwise creates one.
    """
    ing = Ingredient.query.get(ingredient_id)
    if not ing:
        return None

    existing = _existing_unpurchased(ingredient_id)
    if existing:
        existing.quantity_needed += quantity
        return existing

    item = ShoppingListItem(
        ingredient_id=ingredient_id,
        quantity_needed=quantity,
        unit=ing.serving_unit,
        added_from=source,
    )
    db.session.add(item)
    db.session.flush()
    return item


def add_recipe(recipe, servings):
    """
    For each ingredient in the (flattened) recipe, calculate the gap between
    quantity needed and inventory on hand. Add only the gap. Returns the list
    of (ShoppingListItem, qty_added) tuples that were actually touched, plus
    an "ignored" list of (ingredient, reason) for ones skipped.

    Returns (touched, skipped) or None on circular reference.
    """
    try:
        flat = flatten_recipe(recipe, servings)
    except ValueError:
        return None

    touched = []
    skipped = []
    for ing_id, qty_needed in flat.items():
        inv = InventoryItem.query.filter_by(ingredient_id=ing_id).first()
        on_hand = inv.quantity_on_hand if inv else 0
        gap = qty_needed - on_hand
        if gap <= 0:
            ing = Ingredient.query.get(ing_id)
            skipped.append((ing, "covered"))
            continue
        item = add_ingredient(ing_id, gap, source=recipe.name)
        if item is not None:
            touched.append((item, gap))
    return touched, skipped


def toggle_purchased(item):
    """
    Flip purchased flag. When marking purchased, add quantity to inventory.
    When un-marking, deduct it back. Mirrors tracking.delete_log restore.
    """
    if not item.purchased:
        item.purchased = True
        inv = get_or_create_item(item.ingredient_id)
        inv.quantity_on_hand += item.quantity_needed
    else:
        item.purchased = False
        inv = get_or_create_item(item.ingredient_id)
        inv.quantity_on_hand -= item.quantity_needed
    return item
