from datetime import datetime
from app import db


class Ingredient(db.Model):
    __tablename__ = "ingredients"

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    brand = db.Column(db.String(200))
    serving_size = db.Column(db.Float, nullable=False)
    serving_unit = db.Column(db.String(50), nullable=False)
    calories = db.Column(db.Float, nullable=False, default=0)
    protein = db.Column(db.Float, nullable=False, default=0)
    carbs = db.Column(db.Float, nullable=False, default=0)
    fat = db.Column(db.Float, nullable=False, default=0)
    fiber = db.Column(db.Float)
    sugar = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "brand": self.brand,
            "servingSize": self.serving_size,
            "servingUnit": self.serving_unit,
            "calories": self.calories,
            "protein": self.protein,
            "carbs": self.carbs,
            "fat": self.fat,
            "fiber": self.fiber,
            "sugar": self.sugar,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
        }


class Recipe(db.Model):
    __tablename__ = "recipes"

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    total_servings = db.Column(db.Float, nullable=False)
    instructions = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    recipe_ingredients = db.relationship(
        "RecipeIngredient",
        foreign_keys="[RecipeIngredient.recipe_id]",
        cascade="all, delete-orphan",
        lazy="select",
    )

    log_entries = db.relationship(
        "DailyLogEntry",
        backref="recipe",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "totalServings": self.total_servings,
            "instructions": self.instructions,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
        }


class RecipeIngredient(db.Model):
    __tablename__ = "recipe_ingredients"

    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id"), nullable=False)
    ingredient_id = db.Column(db.Integer, db.ForeignKey("ingredients.id"), nullable=True)
    sub_recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id"), nullable=True)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(50), nullable=False)

    ingredient = db.relationship("Ingredient")
    sub_recipe = db.relationship("Recipe", foreign_keys="[RecipeIngredient.sub_recipe_id]")


class UserGoals(db.Model):
    __tablename__ = "user_goals"

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.String(100), nullable=False, unique=True)
    daily_calories = db.Column(db.Float, nullable=False, default=2000)
    daily_protein = db.Column(db.Float, nullable=False, default=150)
    daily_carbs = db.Column(db.Float, nullable=False, default=250)
    daily_fat = db.Column(db.Float, nullable=False, default=65)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "dailyCalories": self.daily_calories,
            "dailyProtein": self.daily_protein,
            "dailyCarbs": self.daily_carbs,
            "dailyFat": self.daily_fat,
            "updatedAt": self.updated_at.isoformat(),
        }


class DailyLogEntry(db.Model):
    __tablename__ = "daily_log_entries"

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False, index=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id"), nullable=False)
    servings = db.Column(db.Float, nullable=False)
    logged_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self, macros=None):
        d = {
            "id": self.id,
            "date": self.date.isoformat(),
            "recipeId": self.recipe_id,
            "recipeName": self.recipe.name if self.recipe else None,
            "servings": self.servings,
            "loggedAt": self.logged_at.isoformat(),
        }
        if macros is not None:
            d["macros"] = macros
        return d
