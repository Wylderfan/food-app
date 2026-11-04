"""Unit conversion and conservative recipe expansion, using no real database."""
import unittest
from types import SimpleNamespace as NS
from app.utils.units import convert_quantity, normalize_unit
from app.utils.inventory import flatten_recipe
from app import create_app, db
from app.models import Recipe


def ingredient_line(quantity=100, unit='g', stock_unit='g', ingredient_id=1):
    return NS(ingredient_id=ingredient_id, sub_recipe_id=None,
              ingredient=NS(serving_unit=stock_unit), quantity=quantity, unit=unit)


def recipe(ident=1, lines=None, servings=2):
    return NS(id=ident, name='Test', total_servings=servings,
              recipe_ingredients=lines if lines is not None else [ingredient_line()])


def nested(child, quantity=1, unit='serving'):
    return NS(ingredient_id=None, sub_recipe_id=child.id, sub_recipe=child,
              quantity=quantity, unit=unit)


class UnitTests(unittest.TestCase):
    def test_compatible_conversions_and_aliases(self):
        for amount, source, target, expected in [
                (0.2, 'kg', 'g', 200), (500, 'grams', 'kg', 0.5),
                (2, 'L', 'ml', 2000), (250, 'ml', 'litres', 0.25),
                (3, 'pieces', 'each', 3), (1, 'unit', 'count', 1)]:
            self.assertEqual(convert_quantity(amount, source, target), expected)
        self.assertEqual(normalize_unit(' GRAMS '), 'g')

    def test_reject_unknown_and_incompatible_units(self):
        for source, target in [('g', 'ml'), ('ml', 'count'), ('can', 'can'),
                               ('cup', 'ml'), ('', 'g'), (None, 'g'), ([], 'g')]:
            with self.subTest(source=source, target=target), self.assertRaises(ValueError):
                convert_quantity(1, source, target)

    def test_reject_bad_and_overflow_quantities(self):
        for value in (0, -1, float('nan'), float('inf'), True, None, 'x'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                convert_quantity(value, 'g', 'g')
        with self.assertRaises(ValueError):
            convert_quantity(1e308, 'kg', 'g')

    def test_nested_repeated_lines_scale_and_combine(self):
        child = recipe(2, [ingredient_line(0.2, 'kg')], servings=2)
        root = recipe(1, [nested(child, 2), nested(child, 1), ingredient_line(50)], servings=2)
        self.assertEqual(flatten_recipe(root, 4), {1: 700})

    def test_reject_cycles_and_missing_references(self):
        root = recipe()
        root.recipe_ingredients = [nested(root)]
        with self.assertRaises(ValueError):
            flatten_recipe(root, 1)
        line = ingredient_line()
        line.ingredient = None
        with self.assertRaises(ValueError):
            flatten_recipe(recipe(lines=[line]), 1)
        line.ingredient_id = None
        with self.assertRaises(ValueError):
            flatten_recipe(recipe(lines=[line]), 1)
        line = ingredient_line()
        line.sub_recipe_id = 2
        with self.assertRaises(ValueError):
            flatten_recipe(recipe(lines=[line]), 1)

    def test_reject_empty_invalid_recipe_and_nested_units(self):
        invalid = [recipe(lines=[]), recipe(servings=0), recipe(servings=float('nan')),
                   recipe(lines=[ingredient_line(-1)]), recipe(lines=[ingredient_line(float('inf'))]),
                   recipe(lines=[nested(recipe(2), unit='kg')])]
        for obj in invalid:
            with self.subTest(obj=obj), self.assertRaises(ValueError):
                flatten_recipe(obj, 1)
        for portions in (0, -1, True, float('inf')):
            with self.assertRaises(ValueError):
                flatten_recipe(recipe(), portions)


class UnitRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_overrides={'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'ENABLE_NUTRITION': False})
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()
        response = self.client.post('/api/ingredients', json={'name': 'Rice', 'servingUnit': 'g'})
        self.ingredient_id = response.json['id']

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_api_preserves_convertible_line_unit(self):
        response = self.client.post('/api/recipes', json={'name': 'Rice bowl', 'totalServings': 2,
            'ingredients': [{'ingredientId': self.ingredient_id, 'quantity': 0.2, 'unit': 'kg'}]})
        self.assertEqual(response.status_code, 201, response.json)
        obj = db.session.get(Recipe, response.json['id'])
        self.assertEqual(obj.recipe_ingredients[0].unit, 'kg')
        self.assertEqual(flatten_recipe(obj, 2), {self.ingredient_id: 200})

    def test_api_rejects_incompatible_unit(self):
        response = self.client.post('/api/recipes', json={'name': 'Bad', 'totalServings': 2,
            'ingredients': [{'ingredientId': self.ingredient_id, 'quantity': 200, 'unit': 'ml'}]})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(Recipe.query.count(), 0)

    def test_form_preserves_compatible_units_and_preview_uses_conversion(self):
        response = self.client.post('/recipes/new', data={'name': 'Rice form', 'total_servings': 2,
            'item_type': 'ingredient', 'item_ref_id': self.ingredient_id,
            'item_quantity': '0.2', 'item_unit': 'kg'})
        self.assertEqual(response.status_code, 302)
        obj = Recipe.query.one()
        self.assertEqual(flatten_recipe(obj, 2), {self.ingredient_id: 200})
        html = self.client.get('/recipes/%d/edit' % obj.id).data.decode()
        self.assertIn('quantityInStockUnit', html)
        self.assertNotIn('placeholder="unit" readonly', html)

    def test_optional_nutrition_uses_converted_quantity(self):
        from app.models import Ingredient
        from app.utils.macros import calculate_recipe_macros
        ing = db.session.get(Ingredient, self.ingredient_id)
        ing.serving_size = 100
        ing.calories = 350
        db.session.commit()
        response = self.client.post('/api/recipes', json={'name': 'Rice bowl', 'totalServings': 2,
            'ingredients': [{'ingredientId': self.ingredient_id, 'quantity': 0.2, 'unit': 'kg'}]})
        obj = db.session.get(Recipe, response.json['id'])
        total, per_serving = calculate_recipe_macros(obj)
        self.assertEqual(total['calories'], 700)
        self.assertEqual(per_serving['calories'], 350)
