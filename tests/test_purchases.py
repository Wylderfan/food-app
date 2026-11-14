from uuid import uuid4
from decimal import Decimal
from datetime import datetime
import unittest
import test_cooking as cooking
from app import db
from app.models import PurchaseReceipt, PurchaseVoid, PurchaseLink, ShoppingListItem, Ingredient, PantryCertainty, InventoryItem
from app.utils.purchases import cost_summary, shopping_identity


class PurchaseTests(unittest.TestCase):
    setUp = cooking.CookingTests.setUp
    tearDown = cooking.CookingTests.tearDown
    amount = cooking.CookingTests.amount
    preview = cooking.CookingTests.preview
    confirm = cooking.CookingTests.confirm
    concurrent = cooking.CookingTests.concurrent
    # Reuse isolated production-config SQLite fixture and concurrent HTTP helper.
    def payload(self, **updates):
        data=dict(token=str(uuid4()), date='2026-11-14', store='Demo shop', currency='GBP',
                  ingredient_id_0=str(self.i), quantity_0='0.2', unit_0='kg', price_0='2.45')
        data.update(updates)
        return data

    def buy(self, data):
        return self.client.post('/purchases/new',data=data,follow_redirects=True)

    def test_purchase_repeat_prices_and_void(self):
        data=self.payload();self.buy(data);self.buy(data)
        self.assertEqual(self.amount(),700)
        with self.app.app_context():
            receipt=PurchaseReceipt.query.one()
            self.assertEqual(Decimal(receipt.total),Decimal('2.4500'))
            self.assertEqual(receipt.lines[0]['stock_quantity'],200)
            self.assertEqual(receipt.lines[0]['price'],'2.45')
            db.session.get(Ingredient,self.i).name='Renamed';db.session.commit()
            self.assertEqual(PurchaseReceipt.query.one().lines[0]['name'],'Rice')
        self.client.post('/purchases/'+data['token']+'/void')
        self.client.post('/purchases/'+data['token']+'/void')
        self.buy(data)
        self.assertEqual(self.amount(),500)
        with self.app.app_context():
            self.assertEqual(PurchaseReceipt.query.count(),1);self.assertEqual(PurchaseVoid.query.count(),1)

    def test_multiline_same_ingredient_aggregated_void(self):
        data=self.payload(ingredient_id_1=str(self.i),quantity_1='300',unit_1='g',price_1='1.55')
        self.buy(data);self.assertEqual(self.amount(),1000)
        with self.app.app_context():self.assertEqual(Decimal(PurchaseReceipt.query.one().total),Decimal('4'))
        self.client.post('/purchases/'+data['token']+'/void');self.assertEqual(self.amount(),500)

    def test_invalid_line_rolls_back_all(self):
        for changes in [dict(price_0='NaN'),dict(price_0='-1'),dict(price_0='1.12345'),dict(quantity_0='inf'),
                        dict(unit_0='ml'),dict(currency='GBP/USD'),dict(date='bad'),dict(store=''),
                        dict(ingredient_id_1=str(self.i),quantity_1='1',unit_1='cup',price_1='2')]:
            self.buy(self.payload(**changes));self.assertEqual(self.amount(),500)
        with self.app.app_context():self.assertEqual(PurchaseReceipt.query.count(),0)

    def test_unknown_preserved_and_voidable(self):
        self.client.post(f'/inventory/{self.i}/correct',data={'mode':'some'})
        data=self.payload();self.buy(data)
        self.assertIsNone(self.client.get('/api/inventory').json[0]['quantityOnHand'])
        self.client.post('/purchases/'+data['token']+'/void')
        self.assertEqual(self.amount(),500)
        self.assertIsNone(self.client.get('/api/inventory').json[0]['quantityOnHand'])

    def test_correction_blocks_void(self):
        data=self.payload();self.buy(data)
        self.client.post(f'/inventory/{self.i}/correct',data={'mode':'known','quantity':700})
        response=self.client.post('/purchases/'+data['token']+'/void',follow_redirects=True)
        self.assertIn(b'Cannot safely void',response.data);self.assertEqual(self.amount(),700)

    def test_consumed_stock_blocks_void_without_negative_stock(self):
        data=self.payload();self.buy(data)
        token=self.preview(6);self.confirm(token)
        self.client.post('/purchases/'+data['token']+'/void');self.assertEqual(self.amount(),100)
        with self.app.app_context():self.assertEqual(PurchaseVoid.query.count(),0)

    def test_void_preserves_other_additions_and_cook_undo(self):
        data=self.payload();self.buy(data)
        token=self.preview();self.confirm(token)
        self.client.post('/inventory/add',data={'ingredient_id':self.i,'quantity':20})
        self.client.post('/purchases/'+data['token']+'/void');self.assertEqual(self.amount(),320)
        self.client.post('/cook/'+token+'/undo');self.assertEqual(self.amount(),520)

    def linked_payload(self):
        self.client.post('/shopping-list/add-ingredient',data={'ingredient_id':self.i,'quantity':200})
        with self.app.app_context():
            item=ShoppingListItem.query.filter_by(purchased=False).one()
            return self.payload(shopping_id=str(item.id),shopping_created=shopping_identity(item))

    def test_linked_purchase_cannot_stock_twice_or_legacy_undo(self):
        data=self.linked_payload();self.buy(data)
        second={**data,'token':str(uuid4())};self.buy(second)
        self.assertEqual(self.amount(),700)
        self.assertEqual(self.client.put('/api/shopping-list/'+data['shopping_id']+'/toggle-purchased').status_code,409)
        self.assertEqual(self.amount(),700)
        self.client.post('/shopping-list/clear-purchased')
        with self.app.app_context():
            self.assertEqual(PurchaseReceipt.query.count(),1);self.assertEqual(PurchaseLink.query.count(),1)
        # SQLite can reuse the cleared shopping ID; identity includes creation timestamp.
        fresh=self.linked_payload();self.buy(fresh);self.assertEqual(self.amount(),900)
        self.buy(second);self.assertEqual(self.amount(),900)

    def test_historical_purchased_rows_remain_readable_without_readding(self):
        with self.app.app_context():
            item=ShoppingListItem(ingredient_id=self.i,quantity_needed=200,unit='g',purchased=True)
            db.session.add(item);db.session.commit();ident=item.id
        response=self.client.get('/purchases/new?shopping_id='+str(ident),follow_redirects=True)
        self.assertIn(b'already completed',response.data)
        self.assertEqual(self.amount(),500)
        self.assertEqual(self.client.get('/api/shopping-list').json[0]['purchased'],True)

    def test_comparisons_currency_and_equivalent_units_only(self):
        self.buy(self.payload(price_0='2',unit_0='kg',quantity_0='1'))
        self.buy(self.payload(price_0='1',unit_0='g',quantity_0='500'))
        self.buy(self.payload(currency='USD',price_0='4',unit_0='kg',quantity_0='1'))
        with self.app.app_context():
            totals,groups=cost_summary(PurchaseReceipt.query.all(),set())
            self.assertEqual(totals['GBP']['net'],Decimal('3'));self.assertEqual(totals['USD']['net'],Decimal('4'))
            self.assertEqual(len(groups),2)
            gbp=next(g for g in groups if g[0]['currency']=='GBP')
            self.assertEqual([r['unit_price'] for r in gbp],[Decimal('.002'),Decimal('.002')])

    def test_parallel_duplicate_and_linked_receipts(self):
        data=self.payload()
        self.concurrent([('/purchases/new',data)]*2);self.assertEqual(self.amount(),700)
        self.concurrent([('/purchases/'+data['token']+'/void',{})]*2);self.assertEqual(self.amount(),500)
        data=self.linked_payload()
        # Conflict returns rendered form/history redirect, but must never add twice.
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(2) as pool:
            list(pool.map(lambda payload:self.app.test_client().post('/purchases/new',data=payload),[data,{**data,'token':str(uuid4())}]))
        self.assertEqual(self.amount(),700)

    def test_missing_stock_new_purchase(self):
        with self.app.app_context():InventoryItem.query.delete();db.session.commit()
        self.buy(self.payload());self.assertEqual(self.amount(),200)

    def test_prices_are_immutable(self):
        self.buy(self.payload())
        with self.app.app_context():
            receipt=PurchaseReceipt.query.one();receipt.store='Overwrite'
            with self.assertRaises(ValueError):db.session.commit()
            db.session.rollback()
            self.assertEqual(PurchaseReceipt.query.one().store,'Demo shop')

    def test_parallel_purchase_and_cook_revalidate_without_lost_stock(self):
        from app.models import CookEvent
        token=self.preview();data=self.payload()
        self.concurrent([('/cook/confirm',{'token':token}),('/purchases/new',data)])
        with self.app.app_context():
            self.assertEqual(self.amount(),700-200*CookEvent.query.count())
        a,b=self.payload(),self.payload()
        before=self.amount()
        self.concurrent([('/purchases/new',a),('/purchases/new',b)])
        self.assertEqual(self.amount(),before+400)

    def test_additive_upgrade_keeps_existing_data(self):
        from app import create_app
        from app.models import CookPreview, CookEvent, CookUndo, StockEpoch
        with self.app.app_context():
            # Simulate PR #3 data before the additive history tables existed.
            for model in (PurchaseLink,PurchaseVoid,PurchaseReceipt,CookUndo,CookEvent,CookPreview,StockEpoch):
                model.__table__.drop(db.engine)
        upgraded=create_app('production',{'TESTING':True,'SECRET_KEY':'test','ENABLE_NUTRITION':False,
            'SQLALCHEMY_DATABASE_URI':self.app.config['SQLALCHEMY_DATABASE_URI']})
        with upgraded.app_context():
            self.assertEqual(Ingredient.query.one().name,'Rice')
            self.assertEqual(InventoryItem.query.one().quantity_on_hand,500)
            self.assertEqual(PurchaseReceipt.query.count(),0)
            db.session.remove();db.engine.dispose()
        self.buy(self.payload());self.assertEqual(self.amount(),700)

    def test_price_comparisons_do_not_merge_reused_ingredient_ids(self):
        self.buy(self.payload())
        with self.app.app_context():
            # A changed creation identity represents a distinct ingredient lifetime.
            ing=db.session.get(Ingredient,self.i);ing.created_at=datetime(2020,1,1);db.session.commit()
        self.buy(self.payload())
        with self.app.app_context():
            _,groups=cost_summary(PurchaseReceipt.query.all(),set())
            self.assertEqual(len(groups),2)
