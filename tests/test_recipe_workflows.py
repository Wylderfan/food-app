"""Recipe form/API regression checks against a disposable in-memory database."""
import unittest
from app import create_app, db
from app.models import Recipe, RecipeIngredient


class RecipeWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_overrides={'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'ENABLE_NUTRITION': False,
            'SECRET_KEY': 'test-only'})
        self.ctx = self.app.app_context(); self.ctx.push()
        self.client = self.app.test_client()
        self.ingredient = self.client.post('/api/ingredients', json={
            'name': "Bob's rice", 'servingUnit': 'g'}).json['id']

    def tearDown(self):
        db.session.remove(); db.drop_all(); self.ctx.pop()

    def recipe(self, name='Bowl', items=None):
        response = self.client.post('/api/recipes', json={'name': name,
            'totalServings': 2, 'ingredients': items or []})
        self.assertEqual(response.status_code, 201, response.data)
        return response.json['id']

    def test_incomplete_form_row_is_not_silently_dropped(self):
        response = self.client.post('/recipes/new', data={
            'name': 'Keep my name', 'description': 'Keep my notes', 'total_servings': '2',
            'item_type': 'ingredient', 'item_ref_id': self.ingredient,
            'item_quantity': '', 'item_unit': 'g'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'quantity must be a finite number greater than 0', response.data)
        self.assertIn(b'Keep my name', response.data)
        self.assertIn(b'Keep my notes', response.data)
        self.assertIn(b'"refId": "1"', response.data)
        self.assertEqual(Recipe.query.count(), 0)

    def test_api_bad_rows_get_422_without_partial_writes(self):
        for rows in ([{'ingredientId': self.ingredient}],
                     [{'ingredientId': self.ingredient, 'quantity': -1}],
                     [{'ingredientId': self.ingredient, 'quantity': float('inf')}],
                     [{'ingredientId': 9999, 'quantity': 1}],
                     [{'ingredientId': self.ingredient, 'quantity': 1, 'unit': 'cups'}],
                     [None], {}, [{'quantity': 1}],
                     [{'ingredientId': self.ingredient, 'subRecipeId': 1, 'quantity': 1}]):
            with self.subTest(rows=rows):
                response = self.client.post('/api/recipes', json={
                    'name': 'Invalid', 'totalServings': 2, 'ingredients': rows})
                self.assertEqual(response.status_code, 422, response.data)
                self.assertEqual(Recipe.query.count(), 0)

    def test_out_of_range_component_ids_get_validation_not_500(self):
        for ident in (float('inf'), float('-inf'), 10**30, 0, -1):
            with self.subTest(ident=ident):
                response = self.client.post('/api/recipes', json={
                    'name': 'Invalid reference', 'totalServings': 2,
                    'ingredients': [{'ingredientId': ident, 'quantity': 1}]})
                self.assertEqual(response.status_code, 422, response.data)
                self.assertEqual(Recipe.query.count(), 0)
        response = self.client.post('/recipes/new', data={
            'name': 'Invalid reference', 'total_servings': '2',
            'item_type': 'ingredient', 'item_ref_id': str(10**30),
            'item_quantity': '1', 'item_unit': 'g'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Recipe.query.count(), 0)

    def test_nonfinite_and_wrong_type_fields_are_rejected(self):
        for payload in ([1], {'name': 123, 'totalServings': 2},
                        {'name': 'Bad', 'totalServings': float('nan')},
                        {'name': 'Bad', 'totalServings': True},
                        {'name': 'Bad', 'totalServings': 1, 'description': {}}):
            self.assertEqual(self.client.post('/api/recipes', json=payload).status_code, 422)
        for value in ('nan', 'inf', '-1', 'oops', ''):
            response = self.client.post('/recipes/new', data={'name': 'Bad', 'total_servings': value})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(Recipe.query.count(), 0)

    def test_nested_recipe_cycle_and_delete_guard(self):
        child = self.recipe('Sauce')
        parent = self.recipe('Pasta', [{'subRecipeId': child, 'quantity': 1}])
        response = self.client.put(f'/api/recipes/{child}', json={
            'name': 'Sauce', 'totalServings': 2,
            'ingredients': [{'subRecipeId': parent, 'quantity': 1}]})
        self.assertEqual(response.status_code, 422)
        self.assertIn('cannot contain itself', response.json['errors']['items'])
        self.assertEqual(self.client.delete(f'/api/recipes/{child}').status_code, 409)
        self.assertEqual(RecipeIngredient.query.filter_by(recipe_id=child).count(), 0)

    def test_form_create_edit_remove_components_and_preserve_on_error(self):
        response = self.client.post('/recipes/new', data={
            'name': 'Rice', 'total_servings': '2', 'item_type': 'ingredient',
            'item_ref_id': self.ingredient, 'item_quantity': '100', 'item_unit': 'g'})
        self.assertEqual(response.status_code, 302)
        ident = int(response.location.rsplit('/', 1)[1])
        response = self.client.post(f'/recipes/{ident}/edit', data={
            'name': 'Do not save', 'total_servings': '2', 'item_type': 'ingredient',
            'item_ref_id': self.ingredient, 'item_quantity': '-1', 'item_unit': 'g'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(db.session.get(Recipe, ident).name, 'Rice')
        self.assertEqual(RecipeIngredient.query.filter_by(recipe_id=ident).one().quantity, 100)
        response = self.client.post(f'/recipes/{ident}/edit', data={'name': 'Empty', 'total_servings': '3'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(RecipeIngredient.query.filter_by(recipe_id=ident).count(), 0)
        self.assertEqual(self.client.get(f'/recipes/{ident}').status_code, 200)
        self.assertEqual(self.client.post(f'/recipes/{ident}/delete').status_code, 302)
        self.assertIsNone(db.session.get(Recipe, ident))

    def test_blank_creation_default_and_accessible_controls(self):
        html = self.client.get('/recipes/new').text
        self.assertIn('placeholder="e.g. 4"', html)
        import re
        field = re.search(r'<input[^>]*name="total_servings"[^>]*>', html).group()
        self.assertIn('value=""', field)
        ident = self.recipe()
        edit = self.client.get(f'/recipes/{ident}/edit').text
        field = re.search(r'<input[^>]*name="total_servings"[^>]*>', edit).group()
        self.assertIn('value="2.0"', field)
        self.assertIn('aria-label="Remove component"', html)
        self.assertIn('aria-label="Quantity"', html)
