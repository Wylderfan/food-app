import os
import re
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from app import create_app, db
from app.models import Ingredient, InventoryItem, Recipe, RecipeIngredient, CookEvent, CookUndo, DailyLogEntry, ShoppingListItem


class CookingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app('production', {'TESTING': True, 'SECRET_KEY': 'test',
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + self.tmp.name + '/test.db', 'ENABLE_NUTRITION': True})
        self.client = self.app.test_client()
        with self.app.app_context():
            ing = Ingredient(name='Rice', serving_size=1, serving_unit='g')
            recipe = Recipe(name='Egg fried rice fixture', total_servings=2)
            db.session.add_all([ing, recipe]); db.session.flush()
            db.session.add_all([InventoryItem(ingredient_id=ing.id, quantity_on_hand=500),
                RecipeIngredient(recipe_id=recipe.id, ingredient_id=ing.id, quantity=200, unit='g')])
            db.session.commit()
            self.i, self.r = ing.id, recipe.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove(); db.engine.dispose()
        self.tmp.cleanup()

    def amount(self):
        with self.app.app_context():
            return InventoryItem.query.filter_by(ingredient_id=self.i).one().quantity_on_hand

    def preview(self, servings=2):
        response = self.client.post(f'/cook/{self.r}/preview', data={'servings': servings})
        self.assertEqual(response.status_code, 200)
        return re.search(rb'name="token" value="([^"]+)"', response.data)[1].decode()

    def confirm(self, token):
        return self.client.post('/cook/confirm', data={'token': token}, follow_redirects=True)

    def test_preview_confirm_duplicate_edit_undo_retry(self):
        token = self.preview()
        self.assertEqual(self.amount(), 500)
        self.confirm(token); self.confirm(token)
        self.assertEqual(self.amount(), 300)
        with self.app.app_context():
            RecipeIngredient.query.first().quantity = 400
            db.session.commit()
            self.assertEqual(CookEvent.query.count(), 1)
            self.assertEqual(DailyLogEntry.query.count(), 0)
            self.assertEqual(ShoppingListItem.query.count(), 0)
        self.client.post(f'/cook/{token}/undo'); self.client.post(f'/cook/{token}/undo')
        self.assertEqual(self.amount(), 500)
        self.confirm(token)
        self.assertEqual(self.amount(), 500)
        self.assertIn(b'Undone', self.client.get('/cook').data)

    def test_changed_stock_and_recipe_require_new_confirmation(self):
        token = self.preview()
        self.client.post('/inventory/add', data={'ingredient_id': self.i, 'quantity': 10})
        self.assertIn(b'Preview again', self.confirm(token).data)
        self.assertEqual(self.amount(), 510)
        token = self.preview()
        with self.app.app_context():
            RecipeIngredient.query.first().quantity = 100; db.session.commit()
        self.assertIn(b'Preview again', self.confirm(token).data)
        self.assertEqual(self.amount(), 510)

    def test_undo_preserves_later_additions_and_cooks(self):
        first = self.preview(); self.confirm(first)
        second = self.preview(); self.confirm(second)
        self.client.post('/api/inventory/add', json={'ingredientId': self.i, 'quantity': 40})
        self.client.post(f'/cook/{first}/undo')
        self.assertEqual(self.amount(), 340)
        self.client.post(f'/cook/{second}/undo')
        self.assertEqual(self.amount(), 540)

    def test_correction_away_and_back_blocks_undo(self):
        token = self.preview(); self.confirm(token)
        for amount in (250, 300):
            self.client.put(f'/api/inventory/{self.i}', json={'quantityOnHand': amount})
        response = self.client.post(f'/cook/{token}/undo', follow_redirects=True)
        self.assertIn(b'Cannot safely undo', response.data)
        self.assertEqual(self.amount(), 300)
        with self.app.app_context(): self.assertEqual(CookUndo.query.count(), 0)

    def test_same_value_correction_blocks_undo(self):
        token = self.preview(); self.confirm(token)
        self.client.post(f'/inventory/{self.i}/correct', data={'mode':'known','quantity':300})
        self.client.post(f'/cook/{token}/undo')
        self.assertEqual(self.amount(), 300)

    def test_short_unknown_incompatible_missing_invalid(self):
        for servings in ('0', '-1', 'nan', 'inf', '8'):
            self.assertEqual(self.client.post(f'/cook/{self.r}/preview', data={'servings':servings}).status_code,302)
        self.client.post(f'/inventory/{self.i}/correct', data={'mode':'some'})
        self.assertEqual(self.client.post(f'/cook/{self.r}/preview',data={'servings':2}).status_code,302)
        self.client.post(f'/inventory/{self.i}/correct', data={'mode':'known','quantity':500})
        with self.app.app_context():
            RecipeIngredient.query.first().unit='ml';db.session.commit()
        self.assertEqual(self.client.post(f'/cook/{self.r}/preview',data={'servings':2}).status_code,302)
        with self.app.app_context():
            RecipeIngredient.query.first().unit='g';InventoryItem.query.delete();db.session.commit()
        self.assertEqual(self.client.post(f'/cook/{self.r}/preview',data={'servings':2}).status_code,302)

    def concurrent(self, paths):
        barrier=Barrier(len(paths))
        def run(pair):
            client=self.app.test_client();barrier.wait()
            return client.post(pair[0],data=pair[1]).status_code
        with ThreadPoolExecutor(max_workers=len(paths)) as pool:
            self.assertEqual(list(pool.map(run,paths)),[302]*len(paths))

    def test_parallel_duplicate_and_undo(self):
        token=self.preview()
        self.concurrent([('/cook/confirm',{'token':token})]*2)
        self.assertEqual(self.amount(),300)
        self.concurrent([(f'/cook/{token}/undo',{})]*2)
        self.assertEqual(self.amount(),500)

    def test_parallel_distinct_confirmations_revalidate(self):
        a,b=self.preview(4),self.preview(4)
        self.concurrent([('/cook/confirm',{'token':a}),('/cook/confirm',{'token':b})])
        self.assertEqual(self.amount(),100)
        with self.app.app_context(): self.assertEqual(CookEvent.query.count(),1)

    def test_parallel_add_and_cook_no_lost_update(self):
        token=self.preview()
        self.concurrent([('/cook/confirm',{'token':token}),('/inventory/add',{'ingredient_id':self.i,'quantity':20})])
        self.assertIn(self.amount(),(320,520))
        with self.app.app_context():
            self.assertEqual(self.amount(),520-200*CookEvent.query.count())

    def test_eating_log_never_deducts_or_restores(self):
        token=self.preview();self.confirm(token)
        response=self.client.post('/api/log',json={'recipeId':self.r,'servings':1})
        self.assertEqual(response.status_code,201)
        self.assertEqual(self.amount(),300)
        self.client.delete('/api/log/'+str(response.json['id']))
        self.assertEqual(self.amount(),300)

    def test_snapshots_immutable_and_survive_recipe_delete(self):
        token=self.preview();self.confirm(token)
        with self.app.app_context():
            event=db.session.get(CookEvent,token);event.servings=8
            with self.assertRaises(ValueError):db.session.commit()
            db.session.rollback()
            db.session.delete(db.session.get(Recipe,self.r));db.session.commit()
        self.client.post(f'/cook/{token}/undo')
        self.assertEqual(self.amount(),500)
