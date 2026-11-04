import unittest
from app import create_app, db
from app.models import Ingredient, InventoryItem, Recipe, RecipeIngredient, RecipePreference, PantryCertainty
from app.blueprints.cook import availability

class CookabilityTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_overrides={'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'ENABLE_NUTRITION': False, 'SECRET_KEY': 'test'})
        self.ctx = self.app.app_context(); self.ctx.push()
        self.client = self.app.test_client()
        self.ing = Ingredient(name='Rice', serving_size=1, serving_unit='g')
        self.recipe = Recipe(name='Rice bowl', total_servings=2)
        db.session.add_all([self.ing,self.recipe]); db.session.flush()
        db.session.add_all([InventoryItem(ingredient_id=self.ing.id, quantity_on_hand=500), RecipeIngredient(recipe_id=self.recipe.id, ingredient_id=self.ing.id, quantity=0.2, unit='kg')]); db.session.commit()
    def tearDown(self):
        db.session.remove(); db.drop_all(); self.ctx.pop()
    def test_scaled_conversion_and_shortage(self):
        self.assertEqual(availability(self.recipe, 2)['status'], 'Ready to cook')
        result = availability(self.recipe, 6)
        self.assertEqual(result['status'], 'Missing ingredients')
        self.assertAlmostEqual(result['lines'][0]['short'],100)
    def test_unknown_and_exact_correction(self):
        self.client.post(f'/inventory/{self.ing.id}/correct',data={'mode':'some'})
        self.assertEqual(availability(self.recipe,2)['status'],'Check quantity')
        self.assertIsNone(self.client.get('/api/inventory').json[0]['quantityOnHand'])
        self.assertIn(b'Have some',self.client.get('/inventory').data)
        self.client.put(f'/api/inventory/{self.ing.id}',json={'quantityOnHand':500})
        self.assertEqual(availability(self.recipe,2)['status'],'Ready to cook')
        self.client.post(f'/inventory/{self.ing.id}/correct',data={'mode':'out'})
        self.assertEqual(availability(self.recipe,2)['status'],'Missing ingredients')
    def test_invalid_correction_preserves_stock(self):
        for value in ['NaN','inf','-1','bad']:
            self.client.post(f'/inventory/{self.ing.id}/correct',data={'mode':'known','quantity':value})
            self.assertEqual(InventoryItem.query.first().quantity_on_hand,500)
    def test_no_stock_mutation_on_views_and_rating(self):
        for path in ['/cook','/cook?servings=3','/cook?status=Ready+to+cook','/cook?servings=NaN','/inventory']:
            self.assertEqual(self.client.get(path).status_code,200)
        self.client.post(f'/cook/{self.recipe.id}/preference',data={'rating':'5','archived':'1'})
        self.assertNotIn(b'Rice bowl',self.client.get('/cook').data)
        self.assertIn(b'Rice bowl',self.client.get('/cook?archived=1').data)
        self.assertEqual(InventoryItem.query.first().quantity_on_hand,500)
    def test_empty_and_invalid_units_not_ready(self):
        self.recipe.recipe_ingredients[0].unit = 'cup'; db.session.commit()
        self.assertEqual(availability(self.recipe,2)['status'],'Check recipe')
        self.recipe.recipe_ingredients=[];db.session.commit()
        self.assertEqual(availability(self.recipe,2)['status'],'Check recipe')
    def test_preference_preserves_servings_and_filter(self):
        response = self.client.post(f'/cook/{self.recipe.id}/preference', data={'rating':'4','servings':'2','status':'Ready to cook','show_archived':'0'})
        self.assertIn('servings=2.0', response.location)
        self.assertIn('status=Ready+to+cook', response.location)

    def test_recipe_ranking(self):
        from app.utils.helpers import current_profile
        other=Recipe(name='A unrated bowl',total_servings=1);db.session.add(other);db.session.flush()
        db.session.add(RecipeIngredient(recipe_id=other.id,ingredient_id=self.ing.id,quantity=1,unit='g'))
        with self.app.test_request_context():
            profile=current_profile()
        db.session.add(RecipePreference(recipe_id=self.recipe.id,profile_id=profile,rating=5));db.session.commit()
        page=self.client.get('/cook').data
        self.assertLess(page.index(b'Rice bowl'),page.index(b'A unrated bowl'))

if __name__ == '__main__': unittest.main()
