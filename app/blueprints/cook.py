"""Pantry availability is advisory; it never silently changes stock."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import Ingredient, InventoryItem, PantryCertainty, Recipe, RecipePreference
from app.utils.helpers import _float, current_profile, is_finite_number
from app.utils.inventory import flatten_recipe, get_or_create_item

cook_bp = Blueprint('cook', __name__)


def availability(recipe, servings):
    try:
        required = flatten_recipe(recipe, servings)
        if not required:
            raise ValueError('This recipe has no ingredient requirements.')
    except ValueError as exc:
        return {'status': 'Check recipe', 'lines': [], 'error': str(exc)}
    lines = []
    missing = uncertain = False
    for ingredient_id, needed in required.items():
        ingredient = db.session.get(Ingredient, ingredient_id)
        stock = InventoryItem.query.filter_by(ingredient_id=ingredient_id).first()
        certainty = db.session.get(PantryCertainty, ingredient_id)
        unknown = bool(certainty and certainty.amount_unknown)
        available = stock.quantity_on_hand if stock else 0
        if not is_finite_number(available):
            unknown = True
            available = 0
        short = max(0, needed - available)
        if unknown:
            uncertain = True
        elif short > 1e-9:
            missing = True
        lines.append({'name': ingredient.name, 'needed': needed, 'available': available,
                      'short': short, 'unknown': unknown, 'unit': ingredient.serving_unit})
    return {'status': 'Missing ingredients' if missing else 'Check quantity' if uncertain else 'Ready to cook',
            'lines': lines, 'error': None}


@cook_bp.route('/cook')
def index():
    servings = _float(request.args.get('servings', '1'))
    if servings is None or servings <= 0:
        flash('Choose a finite, positive serving count.', 'error')
        servings = 1
    status = request.args.get('status', '')
    archived = request.args.get('archived') == '1'
    rows = []
    for recipe in Recipe.query.all():
        preference = db.session.get(RecipePreference, (recipe.id, current_profile()))
        if bool(preference and preference.archived) != archived:
            continue
        result = availability(recipe, servings)
        if status and result['status'] != status:
            continue
        rows.append({'recipe': recipe, 'preference': preference, **result})
    order = {'Ready to cook': 0, 'Check quantity': 1, 'Missing ingredients': 2, 'Check recipe': 3}
    rows.sort(key=lambda row: (order[row['status']], -(row['preference'].rating or 0) if row['preference'] else 0, row['recipe'].name.lower(), row['recipe'].id))
    return render_template('cook/list.html', rows=rows, servings=servings, status=status, archived=archived)


@cook_bp.route('/cook/<int:recipe_id>/preference', methods=['POST'])
def preference(recipe_id):
    db.get_or_404(Recipe, recipe_id)
    rating_text = request.form.get('rating', '')
    if rating_text not in ('', '1', '2', '3', '4', '5'):
        flash('Rating must be between 1 and 5, or unrated.', 'error')
        return redirect(url_for('cook.index'))
    pref = db.session.get(RecipePreference, (recipe_id, current_profile()))
    if pref is None:
        pref = RecipePreference(recipe_id=recipe_id, profile_id=current_profile())
        db.session.add(pref)
    pref.rating = int(rating_text) if rating_text else None
    pref.archived = request.form.get('archived') == '1'
    db.session.commit()
    flash('Recipe preference saved for your current profile.', 'success')
    servings = _float(request.form.get('servings', '1'))
    if servings is None or servings <= 0:
        servings = 1
    return redirect(url_for('cook.index', servings=servings, status=request.form.get('status', ''), archived=request.form.get('show_archived', '')))


@cook_bp.route('/inventory/correct', methods=['POST'])
def correct_selected_stock():
    ingredient_id = request.form.get('ingredient_id', type=int)
    if not ingredient_id:
        flash('Choose an ingredient.', 'error')
        return redirect(url_for('inventory.list_inventory'))
    return correct_stock(ingredient_id)


@cook_bp.route('/inventory/<int:ingredient_id>/correct', methods=['POST'])
def correct_stock(ingredient_id):
    db.get_or_404(Ingredient, ingredient_id)
    mode = request.form.get('mode')
    qty = _float(request.form.get('quantity'))
    if mode not in ('known', 'some', 'out') or (mode == 'known' and (qty is None or qty < 0)):
        flash('Enter a finite non-negative amount, or choose Have some / Out of stock.', 'error')
        return redirect(url_for('inventory.list_inventory'))
    item = get_or_create_item(ingredient_id)
    certainty = db.session.get(PantryCertainty, ingredient_id)
    if certainty is None:
        certainty = PantryCertainty(ingredient_id=ingredient_id)
        db.session.add(certainty)
    certainty.amount_unknown = mode == 'some'
    if mode != 'some':
        item.quantity_on_hand = qty if mode == 'known' else 0
    db.session.commit()
    flash('Pantry status corrected.', 'success')
    return redirect(url_for('inventory.list_inventory'))
