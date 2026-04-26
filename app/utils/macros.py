def calculate_recipe_macros(recipe, _visited=None):
    """
    Returns (total_macros, per_serving_macros) as dicts with keys:
    calories, protein, carbs, fat, fiber, sugar.

    Raises ValueError on circular sub-recipe references.
    """
    if _visited is None:
        _visited = frozenset()
    if recipe.id in _visited:
        raise ValueError(f"Circular reference detected involving recipe '{recipe.name}'")
    _visited = _visited | {recipe.id}

    totals = dict(calories=0.0, protein=0.0, carbs=0.0, fat=0.0, fiber=0.0, sugar=0.0)

    for ri in recipe.recipe_ingredients:
        if ri.ingredient_id and ri.ingredient:
            ing = ri.ingredient
            scale = ri.quantity / ing.serving_size
            totals["calories"] += ing.calories * scale
            totals["protein"] += ing.protein * scale
            totals["carbs"] += ing.carbs * scale
            totals["fat"] += ing.fat * scale
            totals["fiber"] += (ing.fiber or 0.0) * scale
            totals["sugar"] += (ing.sugar or 0.0) * scale
        elif ri.sub_recipe_id and ri.sub_recipe:
            sub_total, _ = calculate_recipe_macros(ri.sub_recipe, _visited)
            scale = ri.quantity / (ri.sub_recipe.total_servings or 1)
            for k in totals:
                totals[k] += sub_total[k] * scale

    servings = recipe.total_servings or 1
    per_serving = {k: v / servings for k, v in totals.items()}
    return totals, per_serving
