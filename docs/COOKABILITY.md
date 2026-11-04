# Pantry and recipe availability increment

This increment implements the first pantry-to-dinner selection step. It does not
yet implement cooking deductions, snapshot undo or purchase cost history.

## Workflow

1. Create an ingredient with its stock unit. Pantry quick correction supports
   exact totals, “have some” (amount unknown), and out of stock. It also works
   for ingredients with no inventory row yet. Add Stock adds to the existing
   amount; it does not convert an uncertain total into a known total.
2. Recipes may use compatible units: g/kg, ml/l, or count/piece/unit/each.
   No density, can/package size, cup, or other guessed conversions are made.
   Existing unsupported lines remain stored, but require correction before
   availability can be claimed. Nested recipes specify servings.
3. Open Cook, choose servings and optionally filter availability. Known sufficient
   recipes are listed first, with higher ratings first within each category.
   Missing amounts are shown explicitly. Unknown amounts say Check quantity.
   Empty, invalid or unsupported recipes say Check recipe, never Ready.
4. Ratings and archive state belong to the current configured profile; pantry
   and recipes remain shared. Profiles are not authentication or access control.
   Archive hides a recipe from your active Cook view; it does not delete it.

## Data and compatibility

`pantry_certainty` and `recipe_preferences` are additive metadata tables created
by the existing app startup. No existing columns are changed or dropped. Existing
inventory amounts are treated as known unless explicitly marked uncertain.
Marking uncertain retains the prior numeric estimate internally without displaying
it as certain; setting an exact amount or out of stock clears uncertainty. Exact
ingredient-form and inventory API updates also clear uncertainty. Deleting the
related ingredient/recipe removes its metadata through ORM cascades.

The inventory API now returns `quantityOnHand: null, amountUnknown: true` for
uncertain amounts. Consumers must not interpret null as zero. Recipe shortfall
shopping skips unknown pantry amounts with a check-pantry message rather than
claiming a precise shortage. Compatible recipe conversion also applies to shopping
and optional legacy nutrition calculations.

Back up existing data and test against a copy first. Startup still cannot upgrade
arbitrary obsolete schemas; the previous ingredient error has not been diagnosed
against the user's database. Never reset a real database to try this branch.

## Verification

Run `.venv/bin/python -m unittest discover -s tests -v` and compileall.
Tests cover compatibility conversions, nested scaling, uncertain/known/missing
stock, rating order and profile isolation, archives, deletion cascades, invalid
input, and prior pantry/recipe/shopping regressions. All fixtures are disposable.
Browser visual QA is tracked separately; passing route tests is not phone QA.

Security limitations from README still apply, including absent authentication and
CSRF protection. This change does not alter deployment or network settings.
