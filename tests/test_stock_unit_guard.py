import unittest
from app import create_app, db
from app.models import Ingredient, InventoryItem, Recipe, RecipeIngredient, ShoppingListItem

class StockUnitGuardTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_overrides={'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'ENABLE_NUTRITION': False})
        self.ctx = self.app.app_context(); self.ctx.push()
        self.client = self.app.test_client()
        self.ing = Ingredient(name='Rice', serving_size=1, serving_unit='g')
        db.session.add(self.ing); db.session.commit()
    def tearDown(self):
        db.session.remove(); db.drop_all(); self.ctx.pop()
    def update(self, unit):
        return self.client.put(f'/api/ingredients/{self.ing.id}', json={'name': 'Changed name', 'servingUnit': unit})
    def test_unreferenced_unit_can_change(self):
        self.assertEqual(self.update('kg').status_code, 200)
        self.assertEqual(self.ing.serving_unit, 'kg')
    def test_even_zero_inventory_prevents_relabeling(self):
        db.session.add(InventoryItem(ingredient_id=self.ing.id, quantity_on_hand=0)); db.session.commit()
        response = self.update('kg')
        self.assertEqual(response.status_code, 422)
        self.assertIn('explicit data conversion', response.json['errors']['servingUnit'])
        self.assertEqual(self.ing.name, 'Rice')
        self.assertEqual(self.ing.serving_unit, 'g')
        self.assertEqual(self.update('g').status_code, 200)
    def test_recipe_reference_prevents_relabeling(self):
        rec = Recipe(name='Rice bowl', total_servings=1); db.session.add(rec); db.session.flush()
        db.session.add(RecipeIngredient(recipe_id=rec.id, ingredient_id=self.ing.id, quantity=100, unit='g')); db.session.commit()
        self.assertEqual(self.update('kg').status_code, 422)
        self.assertEqual(rec.recipe_ingredients[0].quantity, 100)
    def test_shopping_reference_prevents_relabeling(self):
        db.session.add(ShoppingListItem(ingredient_id=self.ing.id, quantity_needed=100, unit='g')); db.session.commit()
        self.assertEqual(self.update('kg').status_code, 422)
    def test_form_rejection_keeps_stock_and_other_fields(self):
        db.session.add(InventoryItem(ingredient_id=self.ing.id, quantity_on_hand=500)); db.session.commit()
        response = self.client.post(f'/ingredients/{self.ing.id}/edit', data={'name': 'New name',
            'serving_unit': 'kg', 'quantity_on_hand': '0.5'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Stock unit cannot be changed', response.data)
        self.assertEqual(self.ing.name, 'Rice')
        self.assertEqual(self.ing.serving_unit, 'g')
        self.assertEqual(InventoryItem.query.one().quantity_on_hand, 500)
