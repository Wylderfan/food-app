# Routes and feature boundaries

This is a reference for the current prototype, not a stable versioned public API.
HTML forms and JSON endpoints coexist. A successful response does not imply
internet-safe authentication, comprehensive input validation, unit conversion or
idempotent replay protection.

## Default pantry-first mode

| Area | HTML routes | JSON routes |
| --- | --- | --- |
| Home | `GET /` | — |
| Ingredients | `GET /ingredients`, `GET/POST /ingredients/new`, `GET/POST /ingredients/<id>/edit`, `POST /ingredients/<id>/delete` | `GET/POST /api/ingredients`, `GET/PUT/DELETE /api/ingredients/<id>` |
| Pantry | `GET /inventory`, `POST /inventory/add` | `GET /api/inventory`, `PUT /api/inventory/<ingredient_id>`, `POST /api/inventory/add` |
| Recipes | `GET /recipes`, `GET /recipes/<id>`, `GET/POST /recipes/new`, `GET/POST /recipes/<id>/edit`, `POST /recipes/<id>/delete` | `GET/POST /api/recipes`, `GET/PUT/DELETE /api/recipes/<id>` |
| Shopping | `GET /shopping-list`, `POST /shopping-list/add-ingredient`, `POST /shopping-list/add-recipe`, `POST /shopping-list/<id>/toggle`, `POST /shopping-list/<id>/delete`, `POST /shopping-list/clear-purchased` | `GET /api/shopping-list`, `POST /api/shopping-list/add-ingredient`, `POST /api/shopping-list/add-recipe`, `PUT /api/shopping-list/<id>/toggle-purchased`, `DELETE /api/shopping-list/<id>`, `DELETE /api/shopping-list/clear-purchased` |

The existing ingredient API uses `servingUnit` as the stock-unit field; it is not
renamed in this refactor. New default-mode ingredient records do not need macro
values or `servingSize`. Ingredient JSON responses omit nutrient fields in default
mode, and recipe responses omit calculated macro summaries; clients relying on
those legacy fields must explicitly opt in or adapt. For field-level details and current validation behavior, see the relevant
blueprint and regression tests rather than guessing from this summary.

Examples of core JSON inputs:

```json
{"name": "Rice", "servingUnit": "g"}
```

```json
{"ingredientId": 1, "quantity": 500}
```

```json
{
  "name": "Simple rice",
  "totalServings": 2,
  "instructions": "Use your usual preparation method.",
  "ingredients": [{"ingredientId": 1, "quantity": 150, "unit": "g"}]
}
```

Use real IDs returned by the app. These examples do not submit data themselves.
Recipe quantities must use compatible stock units; no implicit conversion is
performed. Recipe subcomponents use `subRecipeId` instead of `ingredientId`, with
a quantity measured in portions of the sub-recipe.

## Deferred nutrition routes

With `ENABLE_NUTRITION=false`, the tracking blueprint is not registered and its
routes return 404. USDA search is disabled too. They are unavailable, not silently
redirected to stock-changing operations.

Explicit opt-in exposes the retained compatibility workflows:

- `GET /tracking`: old daily intake view (root `/` stays pantry-first).
- `POST /log`, `POST /log/<id>/delete`: old log mutations.
- `GET/POST /goals`: calorie/macro targets.
- `GET/POST /api/log`, `DELETE /api/log/<id>`.
- `GET/PUT /api/goals`.
- `GET /api/ingredients/search-external?query=...`: optional USDA lookup.

`POST /switch-profile` selects a configured label for legacy profile-scoped data.
It does not establish an authenticated identity or create separate pantry ownership.

Opting in restores legacy behavior, including inventory deduction on meal logging.
Review [the caveats](ARCHITECTURE.md#legacy-nutrition-caveats) before doing so. No
nutrition feature is required for default ingredient, pantry, recipe or shopping use.
