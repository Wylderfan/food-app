"""Manual, immutable receipts. Prices are decimal strings in snapshots."""
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID
import math
import re
from app import db
from app.models import Ingredient, InventoryItem, StockEpoch, PurchaseReceipt, PurchaseLink, PurchaseVoid, ShoppingListItem
from app.utils.units import positive_number, convert_quantity, normalize_unit
from app.utils.inventory import get_or_create_item


def shopping_identity(item):
    return item.created_at.isoformat() if item.created_at else 'legacy-null'


def linked_purchase(item):
    return db.session.get(PurchaseLink, (item.id, shopping_identity(item)))


def record_purchase(data):
    token = str(UUID(data.get('token', '')))
    existing = db.session.get(PurchaseReceipt, token)
    if existing:
        return existing  # First submission wins; never replay edited payload as a new purchase.
    try:
        purchased_on = date.fromisoformat(data.get('date', ''))
    except (ValueError, TypeError):
        raise ValueError('Enter a purchase date in YYYY-MM-DD format.') from None
    store = data.get('store', '').strip()
    currency = data.get('currency', '').strip().upper()
    if not store or len(store) > 200:
        raise ValueError('Enter a store name, up to 200 characters.')
    if not re.fullmatch('[A-Z]{3}', currency):
        raise ValueError('Enter the three-letter currency code from your receipt; no conversion is assumed.')
    raw_lines = data.get('lines', [])
    if not isinstance(raw_lines, list) or not 1 <= len(raw_lines) <= 50:
        raise ValueError('Enter 1–50 purchase lines.')
    lines, total, seen = [], Decimal('0'), set()
    for raw in raw_lines:
        try:
            ingredient_id = int(raw.get('ingredient_id', ''))
            ingredient = db.session.get(Ingredient, ingredient_id)
            if ingredient is None:
                raise ValueError('Choose an existing ingredient for every line.')
            quantity = positive_number(raw.get('quantity'))
            unit = normalize_unit(raw.get('unit'))
            stock_quantity = convert_quantity(quantity, unit, ingredient.serving_unit)
            price = Decimal(str(raw.get('price', '')))
            if not price.is_finite() or price < 0 or price > Decimal('9999999999') or price.as_tuple().exponent < -4:
                raise ValueError('Line price must be non-negative, finite, at most 9999999999, with up to four decimal places.')
        except (InvalidOperation, TypeError, OverflowError):
            raise ValueError('Enter valid quantities and actual total prices for every line.') from None
        shopping_id = raw.get('shopping_id')
        if shopping_id not in (None, ''):
            shopping_id = int(shopping_id)
            item = db.session.get(ShoppingListItem, shopping_id)
            if item is not None and (shopping_id in seen or linked_purchase(item)):
                raise ValueError('This shopping row already has purchase history. Open that history; stock was not added again.')
            if (item is None or item.purchased or item.ingredient_id != ingredient_id
                    or raw.get('shopping_created') != shopping_identity(item)):
                raise ValueError('Shopping row changed or was already purchased. Review the list; no stock changed.')
            seen.add(shopping_id)
        else:
            shopping_id = None
        stock = InventoryItem.query.filter_by(ingredient_id=ingredient_id).first()
        if stock and (not math.isfinite(stock.quantity_on_hand) or stock.quantity_on_hand < 0):
            raise ValueError(f'{ingredient.name}: correct invalid/negative pantry stock before recording a purchase.')
        epoch = db.session.get(StockEpoch, ingredient_id)
        # Snapshots preserve price, identity and both original and stock units.
        base_unit = {'kg':'g','l':'ml'}.get(unit, unit)
        base_quantity = convert_quantity(quantity, unit, base_unit)
        lines.append(dict(ingredient_id=ingredient_id, ingredient_created=ingredient.created_at.isoformat() if ingredient.created_at else 'legacy-null', name=ingredient.name, quantity=quantity,
                          unit=unit, stock_unit=ingredient.serving_unit, stock_quantity=stock_quantity,
                          price=str(price), base_unit=base_unit, base_quantity=base_quantity,
                          shopping_id=shopping_id, epoch=epoch.revision if epoch else 0))
        total += price
    db.session.info['ledger_change'] = True
    for line in lines:
        stock = get_or_create_item(line['ingredient_id'])
        updated = stock.quantity_on_hand + line['stock_quantity']
        if not math.isfinite(updated):
            raise ValueError('Stock total is too large. No purchase recorded.')
        stock.quantity_on_hand = updated
        # Preserve PantryCertainty: adding known goods does not establish an unknown total.
        if line['shopping_id']:
            db.session.get(ShoppingListItem, line['shopping_id']).purchased = True
            db.session.add(PurchaseLink(shopping_id=line['shopping_id'], shopping_created=shopping_identity(db.session.get(ShoppingListItem, line['shopping_id'])), token=token))
    receipt = PurchaseReceipt(token=token, purchase_date=purchased_on, store=store,
                              currency=currency, lines=lines, total=total)
    db.session.add(receipt)
    return receipt


def void_purchase(token):
    receipt = db.session.get(PurchaseReceipt, token)
    if receipt is None:
        raise ValueError('Purchase not found.')
    if db.session.get(PurchaseVoid, token):
        return
    # Aggregate repeated ingredients before checking available stock.
    required = {}
    for line in receipt.lines:
        required[line['ingredient_id']] = required.get(line['ingredient_id'], 0) + line['stock_quantity']
        stock = InventoryItem.query.filter_by(ingredient_id=line['ingredient_id']).first()
        ingredient = db.session.get(Ingredient, line['ingredient_id'])
        epoch = db.session.get(StockEpoch, line['ingredient_id'])
        if (stock is None or ingredient is None or ingredient.serving_unit != line['stock_unit']
                or (epoch.revision if epoch else 0) != line['epoch']):
            raise ValueError('Cannot safely void after a pantry correction, deletion or unit change. No stock changed.')
    for ingredient_id, quantity in required.items():
        stock = InventoryItem.query.filter_by(ingredient_id=ingredient_id).one()
        if not math.isfinite(stock.quantity_on_hand) or stock.quantity_on_hand < quantity:
            raise ValueError('Cannot void: purchased stock may already be consumed. No stock changed.')
    db.session.info['ledger_change'] = True
    for ingredient_id, quantity in required.items():
        InventoryItem.query.filter_by(ingredient_id=ingredient_id).one().quantity_on_hand -= quantity
    db.session.add(PurchaseVoid(token=token))
    # Linked shopping rows remain completed; the retained link prevents stale forms
    # and legacy endpoints from re-adding goods. Use a new row for a new purchase.


def cost_summary(receipts, voided):
    totals, comparisons = {}, {}
    for receipt in receipts:
        row = totals.setdefault(receipt.currency, dict(gross=Decimal(0), voided=Decimal(0), net=Decimal(0)))
        row['gross'] += receipt.total
        if receipt.token in voided:
            row['voided'] += receipt.total
            continue
        row['net'] += receipt.total
        for line in receipt.lines:
            key = (line['ingredient_id'], line['ingredient_created'], receipt.currency, line['base_unit'])
            price = Decimal(line['price']) / Decimal(str(line['base_quantity']))
            comparisons.setdefault(key, []).append(dict(name=line['name'], store=receipt.store,
                date=receipt.purchase_date, unit_price=price, currency=receipt.currency, unit=line['base_unit']))
    return totals, list(comparisons.values())
