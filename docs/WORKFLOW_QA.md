# Pantry workflow QA

## Scope

This pass fixes existing form handling; it does not implement the future meal-planning
roadmap or migrate an installed database. Tests use disposable SQLite data.

## Real browser checks

The app was run on a cloud Linux desktop with Python 3.13 and tested by clicking
and typing in Chromium, not only through Flask's test client:

- Create an ingredient with blank optional quantities; edit stock to 500.
- Create another ingredient with initial stock 75, then delete it.
- Cancel ingredient creation; Back restores the unsaved draft and Forward returns
  to the unchanged list.
- Block deleting an ingredient referenced by a recipe.
- Add stock (+50), and verify the displayed total.
- Add a shopping ingredient before any recipes exist.
- Purchase/unpurchase 100 units: inventory changes 500 → 600 → 500.
- Submit a recipe with a selected ingredient but missing quantity: error is shown,
  entered name/servings/selection survive, and correcting the quantity saves it.
- Edit recipe quantity, add/remove an extra component row, cancel recipe deletion.
- Create a nested recipe and add its missing ingredients to shopping.
- Inspect shopping and ingredient form at approximately 402 CSS-pixel viewport
  width (narrow Chromium window at 125% zoom): no horizontal document overflow.

This is responsive desktop testing, not an actual iPhone/Safari test. Chromium's
DevTools were unavailable; no browser security policy was changed.

## Automated coverage

Run `python -m unittest discover -s tests -v`. Tests cover default/legacy feature
boundaries, finite numeric validation, retained invalid form input, safe deletion,
recipe missing quantities/references/cycles, stock/shopping behavior, and rollback
on a simulated historical inventory schema. The schema diagnostic is tested to
leave the database unchanged.

## Ingredient-save error: what is and is not known

Ordinary ingredient creation succeeds on a fresh database in both real browser
and automated tests. The user's exact reported 500 has **not** been confirmed.
A separate regression reproduces a failure using a known historical NOT NULL
inventory column that `create_all()` does not migrate. Save errors now roll back,
retain the entered form and show a useful message; they do not repair that schema.
See the README's read-only schema check and collect the server traceback before
planning any migration. Never delete the existing database as a troubleshooting step.
