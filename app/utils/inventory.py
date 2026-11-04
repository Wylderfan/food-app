from app import db
from app.models import InventoryItem


def flatten_recipe(recipe, servings, _visited=None):
    """Resolve a recipe into quantities in each ingredient's stock unit.

    Reject missing references, unsupported units, non-positive/non-finite
    quantities and cycles rather than reporting an incomplete recipe as ready.
    Repeated references in different branches are intentionally combined.
    """
    from app.utils.units import convert_quantity, positive_number

    if recipe is None:
        raise ValueError("Recipe not found.")
    servings = positive_number(servings, 'Servings')
    total = positive_number(recipe.total_servings, 'Recipe servings')
    key = recipe.id if recipe.id is not None else id(recipe)
    visited = frozenset() if _visited is None else _visited
    if key in visited:
        raise ValueError(f"Circular reference detected involving recipe '{recipe.name}'")
    visited = visited | {key}
    scale = positive_number(servings / total, 'Serving scale')
    result = {}
    if not recipe.recipe_ingredients:
        raise ValueError("Recipe has no ingredients.")

    for ri in recipe.recipe_ingredients:
        quantity = positive_number(ri.quantity, 'Recipe ingredient quantity')
        scaled = positive_number(quantity * scale, 'Scaled quantity')
        if ri.ingredient_id and not ri.sub_recipe_id:
            if ri.ingredient is None:
                raise ValueError("Recipe ingredient no longer exists.")
            amount = convert_quantity(scaled, ri.unit, ri.ingredient.serving_unit)
            result[ri.ingredient_id] = positive_number(
                result.get(ri.ingredient_id, 0.0) + amount, 'Total quantity')
        elif ri.sub_recipe_id and not ri.ingredient_id and ri.sub_recipe is not None:
            if not isinstance(ri.unit, str) or ri.unit.strip().lower() not in ('serving', 'servings'):
                raise ValueError("Sub-recipe quantity must use servings.")
            for ing_id, qty in flatten_recipe(ri.sub_recipe, scaled, visited).items():
                result[ing_id] = positive_number(result.get(ing_id, 0.0) + qty, 'Total quantity')
        else:
            raise ValueError("Recipe line must reference exactly one existing ingredient or sub-recipe.")

    return result


def get_or_create_item(ingredient_id):
    item = InventoryItem.query.filter_by(ingredient_id=ingredient_id).first()
    if not item:
        item = InventoryItem(ingredient_id=ingredient_id)
        db.session.add(item)
        db.session.flush()
    return item


def apply_recipe_to_inventory(recipe, servings, deduct=True):
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
        item = get_or_create_item(ing_id)
        item.quantity_on_hand += qty * sign
    return flat
