from uuid import uuid4
import math
from app import db
from app.models import Ingredient, InventoryItem, StockEpoch, CookPreview, CookEvent, CookUndo, Recipe
from app.utils.inventory import flatten_recipe
from app.utils.units import positive_number


def stock_snapshot(recipe, servings):
    result = []
    for ingredient_id, quantity in sorted(flatten_recipe(recipe, servings).items()):
        ingredient = db.session.get(Ingredient, ingredient_id)
        stock = InventoryItem.query.filter_by(ingredient_id=ingredient_id).first()
        if stock is None or stock.amount_unknown:
            raise ValueError(f'{ingredient.name}: correct the missing or uncertain pantry amount first.')
        if not math.isfinite(stock.quantity_on_hand) or stock.quantity_on_hand < quantity:
            raise ValueError(f'{ingredient.name}: insufficient known stock; correct the pantry first.')
        epoch = db.session.get(StockEpoch, ingredient_id)
        result.append(dict(ingredient_id=ingredient_id, name=ingredient.name,
                           unit=ingredient.serving_unit, quantity=quantity,
                           before=stock.quantity_on_hand, after=stock.quantity_on_hand - quantity,
                           epoch=epoch.revision if epoch else 0))
    return result


def preview(recipe, servings, profile):
    servings = positive_number(servings, 'Servings')
    row = CookPreview(token=str(uuid4()), profile_id=profile, recipe_id=recipe.id,
                      recipe_name=recipe.name, servings=servings,
                      snapshot=stock_snapshot(recipe, servings))
    db.session.add(row)
    return row


def confirm(token, profile):
    existing = db.session.get(CookEvent, token)
    if existing:
        if existing.profile_id != profile:
            raise ValueError('Confirmation belongs to another profile.')
        return existing
    plan = db.session.get(CookPreview, token)
    if not plan or plan.profile_id != profile:
        raise ValueError('Preview not found for this profile. Preview again.')
    recipe = db.session.get(Recipe, plan.recipe_id)
    current = stock_snapshot(recipe, plan.servings)
    if current != plan.snapshot or recipe.name != plan.recipe_name:
        raise ValueError('Pantry or recipe changed. Preview again and explicitly confirm the new deductions.')
    db.session.info['ledger_change'] = True
    for line in plan.snapshot:
        stock = InventoryItem.query.filter_by(ingredient_id=line['ingredient_id']).one()
        stock.quantity_on_hand -= line['quantity']
    row = CookEvent(token=token, profile_id=profile, recipe_id=plan.recipe_id,
                    recipe_name=plan.recipe_name, servings=plan.servings, snapshot=plan.snapshot)
    db.session.add(row)
    return row


def undo(token, profile):
    row = db.session.get(CookEvent, token)
    if not row or row.profile_id != profile:
        raise ValueError('Cook event not found for this profile.')
    if db.session.get(CookUndo, token):
        return
    stocks = []
    for line in row.snapshot:
        stock = InventoryItem.query.filter_by(ingredient_id=line['ingredient_id']).first()
        ingredient = db.session.get(Ingredient, line['ingredient_id'])
        epoch = db.session.get(StockEpoch, line['ingredient_id'])
        if (stock is None or ingredient is None or stock.amount_unknown
                or ingredient.serving_unit != line['unit']
                or (epoch.revision if epoch else 0) != line['epoch']
                or not math.isfinite(stock.quantity_on_hand + line['quantity'])
                or stock.quantity_on_hand < 0):
            raise ValueError('Cannot safely undo after a pantry correction, deletion or unit change. Review stock manually; no stock changed.')
        stocks.append((stock, line))
    db.session.info['ledger_change'] = True
    for stock, line in stocks:
        stock.quantity_on_hand += line['quantity']
    db.session.add(CookUndo(token=token))
