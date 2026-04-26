# Food Tracker Web App — Project Plan

This file is the single source of truth for building the food tracking app. Work through each step in order. Mark steps complete as you go. Each step should be fully functional before moving to the next.

---

## Architecture Overview

The app tracks food intake through a chain of linked data:

```
Ingredients (with macros) → Recipes (with portions) → Daily Log (with goals)
                                 ↓
                            Inventory (auto-deduct on log)
                                 ↓
                          Shopping List (fills gaps)
```

Recipes can nest other recipes as sub-components (e.g., a "burger" recipe containing a "burger sauce" recipe).

---

## Phase 1: Ingredient Database

The foundation. Every other feature depends on ingredients existing with accurate macro data.

### Step 1.1 — Ingredient Data Model

Create the ingredient schema/model with the following fields:

- `id` — unique identifier
- `name` — string, required
- `brand` — string, optional (for distinguishing store-bought items)
- `servingSize` — number, required (e.g., 100)
- `servingUnit` — string, required (e.g., "g", "ml", "piece", "cup", "tbsp")
- `calories` — number per serving
- `protein` — number (grams) per serving
- `carbs` — number (grams) per serving
- `fat` — number (grams) per serving
- `fiber` — number (grams) per serving, optional
- `sugar` — number (grams) per serving, optional
- `createdAt` — timestamp
- `updatedAt` — timestamp

### Step 1.2 — Ingredient CRUD API

Build API routes for ingredients:

- `POST /api/ingredients` — create a new ingredient
- `GET /api/ingredients` — list all ingredients, support `?search=` query param for filtering by name
- `GET /api/ingredients/:id` — get single ingredient with full macro info
- `PUT /api/ingredients/:id` — update an ingredient
- `DELETE /api/ingredients/:id` — delete (should warn if used in recipes)

### Step 1.3 — Ingredient Management UI

Build the user-facing pages:

- **Ingredient list page** — searchable/filterable table or card list showing name, calories, protein, carbs, fat per serving
- **Add/edit ingredient form** — form with all fields from the data model, with validation (no negative numbers, serving size > 0)
- **Delete confirmation** — modal or inline confirmation, showing which recipes would be affected

---

## Phase 2: Recipes

Recipes link to ingredients with specific quantities and define portions.

### Step 2.1 — Recipe Data Model

Create the recipe schema/model:

**Recipe:**

- `id` — unique identifier
- `name` — string, required
- `description` — string, optional
- `totalServings` — number, required (how many portions this recipe makes)
- `instructions` — text, optional
- `createdAt` — timestamp
- `updatedAt` — timestamp

**RecipeIngredient (join table):**

- `id` — unique identifier
- `recipeId` — foreign key to Recipe
- `ingredientId` — foreign key to Ingredient (nullable if sub-recipe)
- `subRecipeId` — foreign key to Recipe (nullable if ingredient) — enables nesting
- `quantity` — number, required (how much of the ingredient is used in the FULL recipe)
- `unit` — string, required (must be compatible with the ingredient's serving unit for macro calculation)

Constraint: exactly one of `ingredientId` or `subRecipeId` must be set, never both, never neither.

### Step 2.2 — Recipe Macro Calculation Logic

Build a utility/service function that computes the macros for a recipe:

1. For each `RecipeIngredient` where `ingredientId` is set:
   - Convert `quantity` to number of servings: `quantity / ingredient.servingSize` (assumes matching units)
   - Multiply each macro by that number of servings
2. For each `RecipeIngredient` where `subRecipeId` is set:
   - Recursively calculate the sub-recipe's total macros
   - Scale by `quantity / subRecipe.totalServings` (treats the sub-recipe quantity as number of servings of that sub-recipe)
3. Sum all macros to get the **full recipe totals**
4. Divide by `totalServings` to get **per-serving macros**

Guard against circular references (recipe A contains recipe B which contains recipe A). Throw an error if detected.

### Step 2.3 — Recipe CRUD API

- `POST /api/recipes` — create recipe with its ingredient list in one request
- `GET /api/recipes` — list all recipes with per-serving macro summary
- `GET /api/recipes/:id` — full recipe detail including ingredients, quantities, computed macros (total and per-serving)
- `PUT /api/recipes/:id` — update recipe and its ingredient list
- `DELETE /api/recipes/:id` — delete (should warn if used as sub-recipe in other recipes)

### Step 2.4 — Recipe Management UI

- **Recipe list page** — shows name, per-serving calories/protein/carbs/fat
- **Add/edit recipe form:**
  - Recipe name, description, total servings, instructions
  - Dynamic ingredient list: each row has a search/select for ingredient OR sub-recipe, quantity, and unit
  - Live macro preview as ingredients are added (show total and per-serving)
  - Ability to add/remove ingredient rows
- **Recipe detail page** — shows full ingredient breakdown, per-serving macros, instructions

---

## Phase 3: Daily Tracking & Goals

Logging what you eat and tracking against daily targets.

### Step 3.1 — Goal Data Model

**UserGoals:**

- `id` — unique identifier
- `dailyCalories` — number, target
- `dailyProtein` — number (grams), target
- `dailyCarbs` — number (grams), target
- `dailyFat` — number (grams), target
- `updatedAt` — timestamp

### Step 3.2 — Daily Log Data Model

**DailyLogEntry:**

- `id` — unique identifier
- `date` — date, required (the day this entry belongs to)
- `recipeId` — foreign key to Recipe
- `servings` — number, required (e.g., 1.5 servings — allows partial)
- `loggedAt` — timestamp

The macros for each entry are calculated at read time: `recipe per-serving macros × servings`.

### Step 3.3 — Daily Tracking API

- `POST /api/log` — log a meal (recipeId + servings + date). This also triggers inventory deduction (see Phase 4).
- `GET /api/log?date=YYYY-MM-DD` — get all entries for a date with computed macros per entry and daily totals
- `DELETE /api/log/:id` — remove a log entry (should restore inventory — see Phase 4)
- `PUT /api/goals` — set or update daily macro goals
- `GET /api/goals` — get current goals

### Step 3.4 — Daily Tracking UI

- **Daily log page** (the main page of the app):
  - Date selector (default to today, allow browsing previous days)
  - **Daily summary bar/card** at the top showing: consumed vs. goal for calories, protein, carbs, fat (progress bars or similar)
  - **Meal log list** — each entry shows: recipe name, servings, macros for that entry
  - **"Log Meal" action** — opens a modal or inline form: search/select recipe, enter servings count, confirm
  - Ability to delete a log entry
- **Goals settings page/section** — form to set daily calorie and macro targets

---

## Phase 4: Inventory

Track what ingredients you have on hand. Auto-deduct when you log a meal.

### Step 4.1 — Inventory Data Model

**InventoryItem:**

- `id` — unique identifier
- `ingredientId` — foreign key to Ingredient (unique — one inventory record per ingredient)
- `quantityOnHand` — number (in the ingredient's `servingUnit`)
- `lowStockThreshold` — number (in the ingredient's `servingUnit`), user-configurable, default 0
- `updatedAt` — timestamp

### Step 4.2 — Inventory Deduction Logic

Build a service function used when a meal is logged:

1. Given a `recipeId` and `servings` count:
2. Flatten the recipe's full ingredient list (resolving sub-recipes recursively)
3. For each ingredient, calculate the total quantity needed: `recipeIngredient.quantity × (servings / recipe.totalServings)`
4. Deduct that quantity from the corresponding `InventoryItem.quantityOnHand`
5. Allow `quantityOnHand` to go negative (indicates you used something you didn't track purchasing)

**On log entry deletion:** reverse the deduction (add the quantities back).

### Step 4.3 — Inventory API

- `GET /api/inventory` — list all inventory items with ingredient name, quantity on hand, unit, and low-stock status
- `PUT /api/inventory/:ingredientId` — manually set quantity on hand and/or low stock threshold (for restocking, corrections)
- `POST /api/inventory/add` — add quantity to an ingredient (for when you buy something and want to add to existing stock)

Note: inventory items are created automatically the first time an ingredient is referenced (either through deduction or manual add). No separate "create" step needed.

### Step 4.4 — Inventory UI

- **Inventory page** — table/list showing:
  - Ingredient name
  - Quantity on hand + unit
  - Low stock threshold
  - Visual indicator if quantity ≤ threshold (highlight, icon, color)
- **Edit controls** — inline or modal to adjust quantity on hand and threshold per item
- **Bulk restock option** — "mark as purchased" from shopping list feeds into this (see Phase 5)

---

## Phase 5: Shopping List

Generate shopping lists from recipes or individual ingredients, checking inventory for gaps.

### Step 5.1 — Shopping List Data Model

**ShoppingListItem:**

- `id` — unique identifier
- `ingredientId` — foreign key to Ingredient
- `quantityNeeded` — number (how much to buy)
- `unit` — string (matches ingredient serving unit)
- `purchased` — boolean, default false
- `addedFrom` — string, optional (e.g., recipe name for traceability, or "manual")
- `createdAt` — timestamp

### Step 5.2 — Shopping List Logic

**Adding a recipe to the shopping list:**

1. Flatten the recipe's ingredient list (resolving sub-recipes), scaled to the requested servings
2. For each ingredient, calculate quantity needed for the requested servings
3. Check `InventoryItem.quantityOnHand` for that ingredient
4. Only add to the shopping list if `quantityNeeded > quantityOnHand`
5. The amount to add = `quantityNeeded - quantityOnHand` (only the gap)
6. If the ingredient is already on the shopping list (unpurchased), increase the quantity rather than adding a duplicate

**Adding an individual ingredient:**

- User selects ingredient and enters quantity directly
- No inventory check (user explicitly wants to buy it)

**Marking as purchased:**

- Set `purchased = true`
- Add the purchased quantity to `InventoryItem.quantityOnHand` automatically

### Step 5.3 — Shopping List API

- `GET /api/shopping-list` — list all items, unpurchased first, then purchased (for history)
- `POST /api/shopping-list/add-ingredient` — add a single ingredient manually (ingredientId + quantity)
- `POST /api/shopping-list/add-recipe` — add all missing ingredients for a recipe (recipeId + servings). Runs the gap logic from 5.2.
- `PUT /api/shopping-list/:id/toggle-purchased` — mark item as purchased or unpurchased. When marking purchased, add to inventory.
- `DELETE /api/shopping-list/:id` — remove an item
- `DELETE /api/shopping-list/clear-purchased` — clear all purchased items from the list

### Step 5.4 — Shopping List UI

- **Shopping list page** — designed for mobile use at the grocery store:
  - Clean, large-tap-target checklist
  - Each item shows: ingredient name, quantity + unit, source (which recipe or "manual")
  - Tap/check to mark purchased (with immediate visual feedback — strikethrough, move to bottom)
  - "Add ingredient" button — search/select ingredient, enter quantity
  - "Add from recipe" button — search/select recipe, enter servings, auto-populates missing ingredients
  - "Clear purchased" button to clean up the list
  - Unpurchased items grouped/sorted logically (alphabetical or by category if categories are added later)

---

## Phase 6: External API Integration (USDA FoodData Central)

Add the option to search and import ingredient data from an external nutrition API instead of manual entry.

### Step 6.1 — API Integration Service

Build a service that queries the USDA FoodData Central API (https://fdc.nal.usda.gov/api-guide):

- `GET https://api.nal.usda.gov/fdc/v1/foods/search?query=TERM&api_key=KEY`
- Parse results to extract: description, serving size, calories, protein, carbs, fat, fiber, sugar
- Handle unit conversions where needed (USDA uses "per 100g" as a common base)
- API key should be stored as an environment variable

### Step 6.2 — API Search Endpoint

- `GET /api/ingredients/search-external?query=chicken+breast` — proxy to USDA, return simplified results matching the app's ingredient schema

### Step 6.3 — Import UI

Modify the "Add Ingredient" form:

- Add a "Search USDA Database" tab/toggle alongside the manual entry form
- Search field that queries the external API
- Results list showing name, calories, protein, carbs, fat per serving
- "Import" button on each result that pre-fills the add ingredient form with the API data
- User can review and adjust values before saving

---

## Notes for the Agent

- **Work one step at a time.** Complete and verify each step before moving on.
- **Each step should result in working, testable functionality.** Don't stub things out for later.
- **Macro calculation is the critical shared logic.** It's used in recipes, daily log, inventory deduction, and shopping list gap calculation. Build it as a well-tested reusable function.
- **Units matter.** The system assumes ingredient quantities in recipes use the same unit as the ingredient's `servingUnit`. If this becomes a pain point, a unit conversion layer can be added later.
- **Sub-recipe recursion** must guard against circular references everywhere it's used (macro calc, inventory deduction, shopping list flattening).
- **Do not ask the user which tech stack to use.** The stack is already set up — build on top of whatever is in the codebase.
