"""Disposable local QA server. Never reads DATABASE_URL or existing app.db."""
import tempfile
from pathlib import Path
from app import create_app, db
from app.models import Ingredient, InventoryItem, Recipe, RecipeIngredient

tmp = tempfile.TemporaryDirectory(prefix='food-app-qa-')
app = create_app('production', {'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(Path(tmp.name)/'qa.db'),
                              'SECRET_KEY':'disposable-browser-qa', 'ENABLE_NUTRITION':False})
with app.app_context():
    rice=Ingredient(name='Rice (demo)',serving_size=1,serving_unit='g')
    egg=Ingredient(name='Egg (demo)',serving_size=1,serving_unit='count')
    recipe=Recipe(name='Egg fried rice (demo)',total_servings=2,instructions='Cook rice, scramble eggs, combine. Disposable QA fixture.')
    db.session.add_all([rice,egg,recipe]);db.session.flush()
    db.session.add_all([InventoryItem(ingredient_id=rice.id,quantity_on_hand=500),InventoryItem(ingredient_id=egg.id,quantity_on_hand=6),
        RecipeIngredient(recipe_id=recipe.id,ingredient_id=rice.id,quantity=200,unit='g'),
        RecipeIngredient(recipe_id=recipe.id,ingredient_id=egg.id,quantity=2,unit='count')]);db.session.commit()
app.run(host='0.0.0.0',port=5057,debug=False,use_reloader=False)
