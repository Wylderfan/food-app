from app import db
from app.models import InventoryItem


def flatten_recipe(recipe, servings, _visited=None):
    """
    Returns {ingredient_id: total_quantity} for `servings` portions of `recipe`,
    resolving sub-recipes recursively. Quantities are in each ingredient's
    serving unit (recipe ingredient `quantity` is assumed to use that unit;
    see PROJECT.md unit note).

    Raises ValueError on circular sub-recipe references.
    """
    if _visited is None:
        _visited = frozenset()
    if recipe.id in _visited:
        raise ValueError(f"Circular reference detected involving recipe '{recipe.name}'")
    _visited = _visited | {recipe.id}

    scale = servings / (recipe.total_servings or 1)
    result = {}

    for ri in recipe.recipe_ingredients:
        if ri.ingredient_id:
            result[ri.ingredient_id] = result.get(ri.ingredient_id, 0.0) + ri.quantity * scale
        elif ri.sub_recipe_id and ri.sub_recipe:
            sub_servings = ri.quantity * scale
            for ing_id, qty in flatten_recipe(ri.sub_recipe, sub_servings, _visited).items():
                result[ing_id] = result.get(ing_id, 0.0) + qty

    return result


def get_or_create_item(profile_id, ingredient_id):
    item = InventoryItem.query.filter_by(
        profile_id=profile_id, ingredient_id=ingredient_id
    ).first()
    if not item:
        item = InventoryItem(profile_id=profile_id, ingredient_id=ingredient_id)
        db.session.add(item)
        db.session.flush()
    return item


def apply_recipe_to_inventory(profile_id, recipe, servings, deduct=True):
    """
    Adjust inventory for `servings` portions of `recipe`. deduct=True decreases
    quantity_on_hand (meal logged); deduct=False increases (log entry removed).
    Auto-creates inventory items for ingredients that have none yet.
    quantity_on_hand may go negative — PROJECT.md 4.2 allows it.

    Returns the flattened {ingredient_id: quantity} dict on success, or None
    if flattening failed (e.g. circular references). Caller decides how to
    surface the failure; this function never raises.
    """
    try:
        flat = flatten_recipe(recipe, servings)
    except ValueError:
        return None

    sign = -1.0 if deduct else 1.0
    for ing_id, qty in flat.items():
        item = get_or_create_item(profile_id, ing_id)
        item.quantity_on_hand += qty * sign
    return flat
