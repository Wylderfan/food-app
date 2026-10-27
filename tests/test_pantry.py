"""Isolated route/regression checks. Never opens the default instance database."""
import unittest
from datetime import date
from unittest.mock import patch
from app import create_app, db
from app.models import Ingredient, Recipe, DailyLogEntry, UserGoals, InventoryItem


class PantryTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_overrides={
            'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'ENABLE_NUTRITION': False, 'SECRET_KEY': 'test-only',
        })
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def ingredient(self, **extra):
        data = {'name': 'Rice', 'servingUnit': 'g', **extra}
        response = self.client.post('/api/ingredients', json=data)
        self.assertEqual(response.status_code, 201)
        return response.json['id']

    def recipe(self, ingredient_id):
        response = self.client.post('/api/recipes', json={
            'name': 'Rice bowl', 'totalServings': 2,
            'ingredients': [{'ingredientId': ingredient_id, 'quantity': 200, 'unit': 'g'}],
        })
        self.assertEqual(response.status_code, 201)
        return response.json['id']

    def test_pages_and_navigation(self):
        for path in ('/', '/ingredients', '/ingredients/new', '/recipes', '/recipes/new', '/inventory', '/shopping-list'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'name="viewport"', response.data)
                self.assertNotIn(b'href="/goals"', response.data)
                self.assertNotIn(b'href="/tracking"', response.data)
                self.assertNotIn(b'Search USDA', response.data)
                self.assertNotIn(b'Macro Preview', response.data)

    def test_no_nutrition_endpoints_or_calls(self):
        with patch('app.blueprints.ingredients.search_foods', side_effect=AssertionError('no network')):
            for path in ('/tracking', '/goals', '/api/log', '/api/goals', '/api/ingredients/search-external?query=rice'):
                self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.post('/api/log', json={}).status_code, 404)

    def test_new_ingredient_needs_no_macros_or_serving_size(self):
        ident = self.ingredient(calories=999, servingSize=100)
        obj = db.session.get(Ingredient, ident)
        self.assertEqual(obj.serving_size, 1)
        self.assertEqual(obj.calories, 0)
        data = self.client.get(f'/api/ingredients/{ident}').json
        self.assertNotIn('calories', data)
        self.assertEqual(data['servingUnit'], 'g')

    def test_form_create_and_edit_preserve_legacy_nutrients(self):
        obj = Ingredient(name='Legacy rice', serving_size=100, serving_unit='g', calories=360,
                         protein=7, carbs=80, fat=1, fiber=0, sugar=0)
        db.session.add(obj); db.session.commit(); ident = obj.id
        response = self.client.post(f'/ingredients/{ident}/edit', data={
            'name': 'Renamed rice', 'serving_unit': 'g', 'quantity_on_hand': '500',
            'calories': '0', 'serving_size': '1',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(obj.calories, 360)
        self.assertEqual(obj.serving_size, 100)
        self.assertEqual(obj.fiber, 0)
        self.assertEqual(obj.sugar, 0)
        self.assertEqual(obj.inventory_items[0].quantity_on_hand, 500)
        self.assertEqual(self.client.get(f'/ingredients/{ident}/edit').status_code, 200)
        response = self.client.post('/ingredients/new', data={'name':'Egg', 'serving_unit':'piece'})
        self.assertEqual(response.status_code, 302)

    def test_api_edit_preserves_legacy_data(self):
        ident = self.ingredient()
        obj = db.session.get(Ingredient, ident)
        obj.calories = 100; obj.serving_size = 50; db.session.commit()
        response = self.client.put(f'/api/ingredients/{ident}', json={'name':'Rice 2', 'servingUnit':'g', 'calories':999})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(obj.calories, 100)
        self.assertEqual(obj.serving_size, 50)

    def test_recipe_pages_and_api_do_not_calculate_macros(self):
        with patch('app.blueprints.recipes.calculate_recipe_macros', side_effect=AssertionError('nutrition invoked')):
            ident = self.recipe(self.ingredient())
            for path in ('/recipes', '/recipes/new', f'/recipes/{ident}', f'/recipes/{ident}/edit', '/api/recipes', f'/api/recipes/{ident}'):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn(b'perServingMacros', response.data)
                self.assertNotIn(b'Macro Preview', response.data)

    def test_recipe_json_script_escaping(self):
        self.ingredient(name='</script><script>alert(1)</script>')
        response = self.client.get('/recipes/new')
        self.assertNotIn(b'</script><script>alert(1)', response.data)
        self.assertIn(b'\\u003c/script\\u003e', response.data)

    def test_inventory_and_shopping_roundtrip(self):
        ident = self.ingredient()
        recipe = self.recipe(ident)
        self.assertEqual(self.client.post('/api/inventory/add', json={'ingredientId':ident, 'quantity':50}).status_code, 200)
        self.assertEqual(self.client.post('/api/shopping-list/add-recipe', json={'recipeId':recipe, 'servings':2}).status_code, 201)
        items = self.client.get('/api/shopping-list').json
        item = items[0]
        self.assertEqual(item['quantityNeeded'], 150)
        path = f"/api/shopping-list/{item['id']}/toggle-purchased"
        self.assertEqual(self.client.put(path).status_code, 200)
        self.assertEqual(self.client.get('/api/inventory').json[0]['quantityOnHand'], 200)
        self.client.put(path)
        self.assertEqual(self.client.get('/api/inventory').json[0]['quantityOnHand'], 50)

    def test_archived_logs_survive_disabled_mode_and_recipe_delete(self):
        ident = self.recipe(self.ingredient())
        db.session.add(DailyLogEntry(profile_id='Default', date=date.today(), recipe_id=ident, servings=1))
        db.session.add(UserGoals(profile_id='Default'))
        db.session.commit()
        self.assertEqual(self.client.delete(f'/api/recipes/{ident}').status_code, 409)
        self.assertEqual(self.client.post(f'/recipes/{ident}/delete').status_code, 302)
        self.assertEqual(DailyLogEntry.query.count(), 1)
        self.assertEqual(UserGoals.query.count(), 1)
        self.assertIsNotNone(db.session.get(Recipe, ident))

    def test_profile_redirect_home(self):
        response = self.client.post('/switch-profile', data={'profile':'Default'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/'))

    def test_legacy_nutrition_opt_in(self):
        app = create_app(config_overrides={'TESTING': True, 'SQLALCHEMY_DATABASE_URI':'sqlite://', 'ENABLE_NUTRITION':True})
        c = app.test_client()
        for path in ('/', '/tracking', '/goals', '/ingredients/new', '/recipes/new'):
            self.assertEqual(c.get(path).status_code, 200)
        self.assertIn(b'Macro Preview', c.get('/recipes/new').data)
        response = c.post('/api/ingredients', json={'name':'Rice', 'servingSize':100, 'servingUnit':'g', 'calories':360})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json['calories'], 360)
        with app.app_context():
            db.session.remove(); db.drop_all()

if __name__ == '__main__':
    unittest.main()
