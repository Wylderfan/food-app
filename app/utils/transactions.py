"""Serialize app writers before reading; SQLite is the production default.

All writers must use this protocol. External SQL writers are outside the guarantee.
"""
from flask import request, jsonify
from sqlalchemy import text, event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from app import db


def install_transactions(app):
    @app.before_request
    def serialize_writes():
        if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
            return
        db.session.rollback()
        try:
            dialect = db.engine.dialect.name
            if dialect == 'sqlite':
                db.session.execute(text('BEGIN IMMEDIATE'))
            elif dialect == 'postgresql':
                db.session.execute(text('SELECT pg_advisory_xact_lock(713209451)'))
            else:
                return jsonify(error='Stock writes require SQLite or PostgreSQL.'), 503
        except OperationalError:
            db.session.rollback()
            return jsonify(error='Pantry is busy. Retry the same confirmation.'), 409

    @app.after_request
    def release_read_or_failed_transaction(response):
        db.session.rollback()
        db.session.info.clear()
        return response


@event.listens_for(Session, 'before_flush')
def mark_corrections(session, context, instances):
    """Detect corrections, including same-value explicit corrections via touch().

    Ledger changes and explicit additive stock actions preserve correction epochs.
    The epoch is separate from quantities so correction-away-and-back is detected.
    """
    from app.models import Ingredient, InventoryItem, PantryCertainty, StockEpoch
    from flask import has_request_context
    additive = has_request_context() and request.endpoint in ('inventory.add_stock', 'inventory.api_add')
    managed = session.info.get('ledger_change') or additive
    ids = set()
    for obj in list(session.dirty) + list(session.deleted):
        state = inspect(obj)
        if isinstance(obj, Ingredient) and (obj in session.deleted or state.attrs.serving_unit.history.has_changes()):
            ids.add(obj.id)
        elif isinstance(obj, PantryCertainty) and (obj in session.deleted or state.attrs.amount_unknown.history.has_changes()):
            ids.add(obj.ingredient_id)
        elif isinstance(obj, InventoryItem) and not managed and (obj in session.deleted or state.attrs.quantity_on_hand.history.has_changes()):
            ids.add(obj.ingredient_id)
    for ingredient_id in ids:
        touch(ingredient_id, session)


def touch(ingredient_id, session=None):
    from app.models import StockEpoch
    session = session or db.session
    row = session.get(StockEpoch, ingredient_id)
    if row is None:
        row = next((r for r in session.new if isinstance(r, StockEpoch) and r.ingredient_id == ingredient_id), None)
    if row is None:
        row = StockEpoch(ingredient_id=ingredient_id, revision=0)
        session.add(row)
    row.revision = (row.revision or 0) + 1
