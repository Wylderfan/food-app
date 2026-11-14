from datetime import date
from uuid import uuid4
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import Ingredient, ShoppingListItem, PurchaseReceipt, PurchaseLink, PurchaseVoid
from app.utils.purchases import record_purchase, void_purchase, cost_summary, linked_purchase, shopping_identity

purchases_bp = Blueprint('purchases', __name__)


@purchases_bp.app_template_filter('money')
def money(value):
    from decimal import Decimal
    return format(Decimal(str(value)), '.4f')


def form_page(form=None):
    form = form or dict(token=str(uuid4()), date=date.today().isoformat())
    ingredients = Ingredient.query.order_by(Ingredient.name).all()
    shopping_id = form.get('shopping_id') or request.args.get('shopping_id', type=int)
    try:
        item = db.session.get(ShoppingListItem, int(shopping_id)) if shopping_id else None
    except (ValueError, TypeError):
        item = None
    if shopping_id and (item is None or item.purchased or linked_purchase(item)):
        flash('This shopping row is already completed or unavailable. Review purchase history; no stock was added.', 'error')
        return redirect(url_for('purchases.history'))
    return render_template('purchases/form.html', form=form, ingredients=ingredients, item=item, shopping_created=shopping_identity(item) if item else '')


@purchases_bp.route('/purchases/new', methods=['GET','POST'])
def new():
    if request.method == 'GET':
        return form_page()
    lines = []
    for index in range(5):
        values = {key:request.form.get(f'{key}_{index}', '') for key in ('ingredient_id','quantity','unit','price')}
        if not any(values.values()):
            continue
        if index == 0:
            values['shopping_id'] = request.form.get('shopping_id')
            values['shopping_created'] = request.form.get('shopping_created')
        lines.append(values)
    try:
        record_purchase(dict(token=request.form.get('token',''), date=request.form.get('date',''),
                             store=request.form.get('store',''), currency=request.form.get('currency',''), lines=lines))
        db.session.commit()
        flash('Purchase recorded. Goods added to stock once; uncertain totals remain uncertain.', 'success')
        return redirect(url_for('purchases.history'))
    except (ValueError, TypeError) as exc:
        db.session.rollback()
        flash(str(exc), 'error')
        return form_page(request.form)


@purchases_bp.route('/purchases')
def history():
    receipts = PurchaseReceipt.query.order_by(PurchaseReceipt.purchase_date.desc(), PurchaseReceipt.created_at.desc()).all()
    voided = {row.token for row in PurchaseVoid.query.all()}
    totals, comparisons = cost_summary(receipts, voided)
    return render_template('purchases/history.html', receipts=receipts, voided=voided, totals=totals, comparisons=comparisons)


@purchases_bp.route('/purchases/<token>/void', methods=['POST'])
def void(token):
    try:
        void_purchase(token)
        db.session.commit()
        flash('Purchase voided; its original stock additions reversed once. Original prices remain in history.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'error')
    return redirect(url_for('purchases.history'))
