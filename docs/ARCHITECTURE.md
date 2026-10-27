# Architecture and data flow

## Request lifecycle

`run.py` creates the app and starts the development server. Production examples
invoke `app:create_app()` through Gunicorn. `config.py` loads environment-backed
settings; `.env` is loaded before those settings are evaluated. The factory accepts
optional `config_overrides` so tests can select an isolated database before the
SQLAlchemy extension is initialized.

`app/__init__.py` initializes SQLAlchemy, imports models, registers blueprints,
adds template globals/error pages and creates missing tables. It is deliberately
small: business logic belongs in utilities/services rather than the factory.

HTML pages use Jinja templates. Forms submit to UI routes; JavaScript in some
pages calls JSON endpoints. The two interfaces share models/utilities but do not
yet use a comprehensive shared validation/service layer.

## Module map

| Module | Responsibility |
| --- | --- |
| `app/blueprints/main.py` | Pantry-first home and profile selection. |
| `ingredients.py` | Ingredient catalogue, manual forms and JSON CRUD; optional USDA search boundary. |
| `inventory.py` | List stock, add quantities, set quantities/thresholds. |
| `recipes.py` | Recipes, nested components and forms/API serialization. |
| `shopping.py` | Shopping checklist, recipe shortfalls, purchased toggles. |
| `tracking.py` | Retained legacy eating log and goals; registered only when nutrition is enabled. |
| `app/utils/inventory.py` | Flatten nested recipes and adjust stock. |
| `app/utils/shopping.py` | Calculate recipe gaps and apply purchase changes. |
| `app/utils/macros.py` | Legacy nutrient calculation, not required by default pantry views. |
| `app/utils/usda.py` | Optional legacy external nutrient search. |
| `app/utils/helpers.py` | Numeric parsing and active legacy profile lookup. |

## Data ownership

The current application has **one shared catalogue/pantry**, not one per profile:

- `Ingredient`: name/brand, base stock unit, low-stock threshold, retained serving
  basis and nutrient fields.
- `InventoryItem`: one row per ingredient; current quantity in that ingredient's unit.
- `Recipe`: instructions and number of portions produced.
- `RecipeIngredient`: either an ingredient amount or a number of sub-recipe portions.
- `ShoppingListItem`: amount to buy, unit, source label, purchased flag.
- `UserGoals`, `DailyLogEntry`: profile-specific legacy nutrition state.

Choosing a profile does not isolate recipes or stock and is not a login. IDs and
numeric database constraints alone are not authorization boundaries.

## Default mode: nutrition deferred

`ENABLE_NUTRITION=false` is the default. The root page is pantry-oriented; daily
tracking/goals are not active navigation or registered routes. The USDA endpoint
is unavailable while disabled. Ingredient and recipe workflows do not require
nutrient values or an external API key. The ingredient form asks for name/unit;
new records use a serving-size basis of 1 for schema compatibility. Editing an
existing ingredient preserves its stored serving basis and nutrition values.

Disabling nutrition does **not** drop tables, delete values, clear history or undo
past deductions. Legacy nutrient values sent to disabled write workflows are not
used to overwrite stored values. Recipes with retained meal history cannot simply
be deleted through the current deletion workflow, protecting that history.

Explicit `ENABLE_NUTRITION=true` opts back into the old workflows, with the daily
page at `/tracking` rather than `/`. This is a compatibility escape hatch, not an
endorsement of the old product model. Read the legacy caveats before enabling it.

## What changes stock today

1. **Manual ingredient/inventory entry:** creates or sets a quantity, or adds a
   restock quantity. These are corrections, not purchase-cost records.
2. **Shopping purchase toggle:** marking purchased adds the checklist quantity;
   unmarking subtracts it. Repeated intentional toggles reverse each other. The
   endpoint is not an idempotent “set purchased=true” event API, so duplicate
   submissions can have surprising results.
3. **Legacy meal logging, only when enabled:** logging portions calls
   `apply_recipe_to_inventory(..., deduct=True)`; deleting a log calculates the
   reverse from the recipe's present contents.

There is **no dedicated cooking event in this refactor**. In default mode adjust
stock manually after cooking until the snapshot-based cooking feature is built.
Eating a leftover portion must eventually be separate from making the original dish.

## Recipe quantities and shopping gaps

`flatten_recipe(recipe, portions)` scales direct ingredient quantities by
`portions / recipe.total_servings`. Nested recipes recurse using the specified
number of sub-recipe portions. Quantities for the same ingredient accumulate.
Cycle detection prevents endless recursion during flattening.

The existing calculations assume a recipe ingredient amount uses its ingredient's
stock unit. They do **not** convert g to kg, ml to cups, or volume to weight merely
because a unit label was entered. Keep units consistent until an explicit validated
conversion layer is added.

Adding a recipe to shopping computes `required - on_hand` for each ingredient and
adds positive gaps to an existing unpurchased row or a new one. Repeating the
operation adds another gap; it is not an idempotent meal plan. Missing inventory is
treated as zero. The app does not yet rank recipes by stock sufficiency or rating.

## Legacy nutrition caveats

- Meal logging means “ate this”, but its inventory effect is closer to “cooked
  this”. This can deduct raw ingredients again when eating leftovers.
- Log undo is calculated from current recipe data, not an immutable deduction
  snapshot. Editing a recipe later can make restoration inaccurate.
- Nutrient calculations rely on consistent units and serving bases. Missing
  nutrition is not proof of zero calories or a nutritionally complete record.
- Keeping the legacy code preserves a path to inspect historical data, but it is
  deliberately not the default experience or the foundation for new cooking logic.

## Transactions, validation and migration limits

Routes generally accumulate changes and call `db.session.commit()` once. This is
not a complete audit/event architecture or proof of concurrency safety. Existing
row parsers and validation need additional hardening before a larger data model is
built. See the roadmap acceptance criteria for atomic cooking snapshots and
repeat-submission protection.

`db.create_all()` is a bootstrap mechanism, not a migration system. This refactor
keeps the schema stable. Before future schema changes, introduce explicit versioned
migrations, back up real data and test upgrades/rollback on a copy.

## Where to extend next

- Put shared ingredient/unit rules in a small reusable service, exercised by both
  HTML and API validation.
- Add a read-only cookability query before adding automatic stock mutations.
- Model cooking as its own transaction and event snapshot, with one-time undo.
- Store actual purchases separately from a disposable shopping checklist.
- Leave nutrition as an optional adapter/feature, never a prerequisite for pantry entry.

Do not add a new framework solely to achieve these separations. The current Flask
foundation can support small, tested increments.
