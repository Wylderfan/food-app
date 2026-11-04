"""Disposable form and stock regressions; no user database or remote services."""
import unittest
from app import create_app, db
from app.models import Ingredient, InventoryItem, ShoppingListItem


class FormTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_overrides={'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'ENABLE_NUTRITION': False,
            'SECRET_KEY': 'isolated-test'})
        self.ctx = self.app.app_context(); self.ctx.push()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove(); db.drop_all(); self.ctx.pop()

    def ingredient(self):
        result = self.client.post('/api/ingredients', json={'name': 'Rice', 'servingUnit': 'g'})
        self.assertEqual(result.status_code, 201)
        return result.json['id']

    def test_normal_ingredient_form_and_blank_optional_values(self):
        for quantity in ('', '0', '25'):
            response = self.client.post('/ingredients/new', data={
                'name': "Bob's rice", 'brand': '', 'serving_unit': 'g',
                'quantity_on_hand': quantity, 'low_stock_threshold': ''}, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'added.', response.data)
        self.assertEqual(Ingredient.query.count(), 3)
        self.assertEqual(InventoryItem.query.one().quantity_on_hand, 25)

    def test_bad_optional_number_preserves_form_without_saving(self):
        for field in ('quantity_on_hand', 'low_stock_threshold'):
            for value in ('nan', 'inf', 'not a number'):
                response = self.client.post('/ingredients/new', data={
                    'name': 'Keep my name', 'serving_unit': 'g', field: value})
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'Enter a finite number.', response.data)
                self.assertIn(b'Keep my name', response.data)
                self.assertEqual(Ingredient.query.count(), 0)

    def test_create_defaults_are_blank_and_edit_values_retained(self):
        response = self.client.get('/ingredients/new').text
        self.assertIn("name=\"quantity_on_hand\" id=\"ingredient-quantity_on_hand\" step=\"any\" placeholder=\"0\"\n                 value=\"\"", response)
        ident = self.ingredient()
        self.client.put(f'/api/inventory/{ident}', json={'quantityOnHand': 35})
        response = self.client.get(f'/ingredients/{ident}/edit').text
        self.assertIn('value="35"', response)
        self.client.post(f'/ingredients/{ident}/edit', data={'name': 'Rice', 'serving_unit': 'g', 'quantity_on_hand': ''})
        self.assertEqual(InventoryItem.query.one().quantity_on_hand, 35)

    def test_nonfinite_json_does_not_corrupt_stock(self):
        ident = self.ingredient()
        for value in (float('nan'), float('inf'), True, 'wrong'):
            for method, url, payload in (
                ('put', f'/api/inventory/{ident}', {'quantityOnHand': value}),
                ('post', '/api/inventory/add', {'ingredientId': ident, 'quantity': value}),
                ('post', '/api/shopping-list/add-ingredient', {'ingredientId': ident, 'quantity': value}),
                ('put', f'/api/ingredients/{ident}', {'name': 'Rice', 'servingUnit': 'g', 'lowStockThreshold': value}),
            ):
                self.assertEqual(getattr(self.client, method)(url, json=payload).status_code, 422)
        self.assertEqual(InventoryItem.query.count(), 0)
        self.assertEqual(ShoppingListItem.query.count(), 0)

    def test_shopping_references_block_ingredient_deletion(self):
        ident = self.ingredient()
        self.client.post('/api/shopping-list/add-ingredient', json={'ingredientId': ident, 'quantity': 3})
        self.assertEqual(self.client.delete(f'/api/ingredients/{ident}').status_code, 409)
        response = self.client.post(f'/ingredients/{ident}/delete', follow_redirects=True)
        self.assertIn(b'Remove this ingredient from the shopping list', response.data)
        self.assertIsNotNone(db.session.get(Ingredient, ident))
        self.assertEqual(self.client.get('/shopping-list').status_code, 200)
        shopping_id = ShoppingListItem.query.one().id
        self.client.delete(f'/api/shopping-list/{shopping_id}')
        self.assertEqual(self.client.delete(f'/api/ingredients/{ident}').status_code, 200)

    def test_purchase_unpurchase_and_repeat_roundtrip(self):
        ident = self.ingredient()
        self.client.post('/inventory/add', data={'ingredient_id': ident, 'quantity': 5})
        self.client.post('/shopping-list/add-ingredient', data={'ingredient_id': ident, 'quantity': 3})
        item = ShoppingListItem.query.one()
        for expected in (8, 5, 8, 5):
            response = self.client.post(f'/shopping-list/{item.id}/toggle', follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(InventoryItem.query.one().quantity_on_hand, expected)

    def test_invalid_stock_shopping_forms_stay_open_and_preserve_input(self):
        ident = self.ingredient()
        for path in ('/inventory/add', '/shopping-list/add-ingredient'):
            response = self.client.post(path, data={'ingredient_id': ident, 'quantity': '-2'})
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'value="-2"', response.data)
            self.assertIn(b'positive quantity', response.data)
            self.assertIn(f'value="{ident}" selected'.encode(), response.data)
        self.assertEqual(InventoryItem.query.count(), 0)
        self.assertEqual(ShoppingListItem.query.count(), 0)

    def test_labels_target_controls_and_edit_does_not_round_stock(self):
        from html.parser import HTMLParser
        class Controls(HTMLParser):
            def __init__(self):
                super().__init__(); self.ids = set(); self.targets = []
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if 'id' in attrs: self.ids.add(attrs['id'])
                if tag == 'label': self.targets.append(attrs.get('for'))
        ident = self.ingredient()
        quantity = 123.456789123
        self.client.put(f'/api/inventory/{ident}', json={'quantityOnHand': quantity})
        for path in ('/ingredients/new', f'/ingredients/{ident}/edit', '/inventory', '/shopping-list'):
            response = self.client.get(path)
            parsed = Controls(); parsed.feed(response.text)
            self.assertTrue(all(target in parsed.ids for target in parsed.targets), path)
        self.assertIn(f'value="{quantity}"', self.client.get(f'/ingredients/{ident}/edit').text)

    def test_historical_inventory_constraint_rolls_back_entire_ingredient_save(self):
        from sqlalchemy import text
        # Simulates a former model column retained by create_all, not a user DB.
        db.session.execute(text('ALTER TABLE inventory_items ADD COLUMN low_stock_threshold FLOAT NOT NULL'))
        db.session.commit()
        with self.assertLogs(self.app.logger, level='ERROR'):
            response = self.client.post('/ingredients/new', data={
                'name': 'Keep draft', 'serving_unit': 'g', 'quantity_on_hand': '5'})
        self.assertEqual(response.status_code, 422)
        self.assertIn(b'Your existing database may need a migration', response.data)
        self.assertIn(b'Keep draft', response.data)
        self.assertNotIn(b'INSERT INTO', response.data)
        self.assertEqual(Ingredient.query.count(), 0)
        self.assertEqual(InventoryItem.query.count(), 0)
        ident = self.ingredient()
        with self.assertLogs(self.app.logger, level='ERROR'):
            response = self.client.post(f'/ingredients/{ident}/edit', data={
                'name': 'Changed name', 'serving_unit': 'g', 'quantity_on_hand': '5'})
        self.assertEqual(response.status_code, 422)
        self.assertIn(b'Changed name', response.data)
        self.assertEqual(db.session.get(Ingredient, ident).name, 'Rice')
        self.assertEqual(InventoryItem.query.count(), 0)

    def test_schema_diagnostic_is_read_only(self):
        import tempfile
        import sqlite3
        from pathlib import Path
        from scripts.check_sqlite_schema import inspect_schema
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'historical.db'
            with sqlite3.connect(path) as connection:
                connection.execute('CREATE TABLE ingredients (id INTEGER PRIMARY KEY, name TEXT)')
                connection.execute('CREATE TABLE inventory_items (id INTEGER PRIMARY KEY, low_stock_threshold FLOAT NOT NULL)')
            before = path.read_bytes()
            warnings = inspect_schema(path)
            self.assertEqual(len(warnings), 2)
            self.assertEqual(path.read_bytes(), before)
            with self.assertRaises(FileNotFoundError):
                inspect_schema(Path(tmp) / 'missing.db')
            self.assertFalse((Path(tmp) / 'missing.db').exists())
