"""Independent edge-case review of pantry certainty and profile preferences."""
import unittest
from app import create_app, db
from app.models import Ingredient, InventoryItem, PantryCertainty, Recipe, RecipeIngredient, RecipePreference
from app.blueprints.cook import availability

class CookReviewTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_overrides={'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'ENABLE_NUTRITION': False, 'SECRET_KEY': 'test', 'PROFILES': 'One,Two'})
        self.ctx = self.app.app_context(); self.ctx.push()
        self.client = self.app.test_client()
        self.ing = Ingredient(name='Rice', serving_size=1, serving_unit='g')
        self.recipe = Recipe(name='Rice bowl', total_servings=1)
        db.session.add_all([self.ing, self.recipe]); db.session.commit()

    def tearDown(self):
        db.session.remove(); db.drop_all(); self.ctx.pop()

    def test_delete_ingredient_removes_certainty(self):
        self.client.post(f'/inventory/{self.ing.id}/correct', data={'mode': 'some'})
        self.assertEqual(PantryCertainty.query.count(), 1)
        self.assertEqual(self.client.delete(f'/api/ingredients/{self.ing.id}').status_code, 200)
        self.assertEqual(PantryCertainty.query.count(), 0)
        self.assertEqual(InventoryItem.query.count(), 0)

    def test_delete_recipe_removes_all_profiles_preferences(self):
        db.session.add_all([RecipePreference(recipe_id=self.recipe.id, profile_id=p, rating=5) for p in ('One', 'Two')])
        db.session.commit()
        self.assertEqual(self.client.delete(f'/api/recipes/{self.recipe.id}').status_code, 200)
        self.assertEqual(RecipePreference.query.count(), 0)

    def test_profile_picker_available_and_preferences_separate(self):
        self.assertIn(b'action="/switch-profile"', self.client.get('/cook').data)
        self.client.post(f'/cook/{self.recipe.id}/preference', data={'rating': '5'})
        self.client.post('/switch-profile', data={'profile': 'Two'})
        self.client.post(f'/cook/{self.recipe.id}/preference', data={'rating': '2'})
        self.assertEqual(db.session.get(RecipePreference, (self.recipe.id, 'One')).rating, 5)
        self.assertEqual(db.session.get(RecipePreference, (self.recipe.id, 'Two')).rating, 2)

    def test_invalid_preference_no_mutation(self):
        self.client.post(f'/cook/{self.recipe.id}/preference', data={'rating': 'NaN', 'archived': '1'})
        self.assertEqual(RecipePreference.query.count(), 0)
        self.assertEqual(self.client.post('/cook/9999/preference', data={'rating': '5'}).status_code, 404)
        self.assertEqual(self.client.post('/inventory/9999/correct', data={'mode': 'some'}).status_code, 404)

    def test_add_does_not_turn_unknown_total_into_exact(self):
        self.client.post(f'/inventory/{self.ing.id}/correct', data={'mode': 'some'})
        self.client.post('/api/inventory/add', json={'ingredientId': self.ing.id, 'quantity': 50})
        self.assertTrue(db.session.get(PantryCertainty, self.ing.id).amount_unknown)
        self.client.put(f'/api/inventory/{self.ing.id}', json={'lowStockThreshold': 5})
        self.assertTrue(db.session.get(PantryCertainty, self.ing.id).amount_unknown)
        self.client.post(f'/inventory/{self.ing.id}/correct', data={'mode': 'known', 'quantity': '100'})
        self.assertFalse(db.session.get(PantryCertainty, self.ing.id).amount_unknown)
        self.assertEqual(InventoryItem.query.one().quantity_on_hand, 100)

    def test_legacy_nonfinite_stock_never_ready(self):
        db.session.add(RecipeIngredient(recipe_id=self.recipe.id, ingredient_id=self.ing.id, quantity=1, unit='g'))
        db.session.add(InventoryItem(ingredient_id=self.ing.id, quantity_on_hand=float('inf')))
        db.session.commit()
        self.assertEqual(availability(self.recipe, 1)['status'], 'Check quantity')
