# Pantry-first roadmap

This is the current product direction. The old nutrition-first proposal is kept
in [docs/archive/nutrition-plan.md](docs/archive/nutrition-plan.md) for reference,
not as an active implementation checklist.

## Goal

Open the app on a phone and answer: **“What can I cook tonight with what I have,
starting with recipes I already like?”** Pantry accuracy can be approximate, but
the app must be honest about missing or uncertain quantities. Nutrition/API work
must not block this core loop.

## Foundation in this refactor

- Keep Flask, SQLAlchemy, Jinja templates and the useful ingredient/recipe/pantry/shopping structure.
- Default to a pantry-first interface; make legacy calories, goals and USDA optional.
- Preserve existing data and make application boundaries understandable.
- Add isolated regression tests and useful operational documentation.

This refactor does **not** deliver the later phases below.

## Phase 1: forgiving pantry

Settle whether everyone shares one pantry (the current data model does), and
which approximate quantities the household is willing to maintain.

- Quick add, restock and correct-stock actions with explicit units.
- Canonical ingredient identity, aliases where useful, and duplicate handling.
- Distinguish “have some / quantity uncertain” from a measured number if needed;
  do not encode uncertainty as zero or silently promise enough for a recipe.
- Validate non-finite/negative inputs according to operation semantics.
- Protect mutation routes with CSRF safeguards and define access control before
  use with important household data or broader access.

**Acceptance:** add an ingredient without nutrition details; restock and correct
it comfortably on a phone; no silent unit conversion or duplicate stock records.

## Phase 2: recipes and what-to-cook ranking

- Save familiar recipes and a simple personal/household rating.
- Flatten sub-recipes consistently; reject cycles and invalid ingredient references.
- Match quantities only after unit compatibility is checked. Introduce explicit
  supported conversions (e.g. g/kg), not guessed mass/volume conversions.
- Separate “can cook”, “check stock” and “missing items”; rank cookable favorites
  first and explain missing ingredients instead of hiding them.

**Acceptance:** predictable rankings from fixture pantry/recipe data; a recipe
requiring milk in ml cannot be approved using an unrelated mass value; uncertain
stock is surfaced rather than treated as sufficient.

## Phase 3: cooking event and safe undo

Cooking, eating and shopping are different events. A dedicated cooking action
should deduct raw ingredients once when the dish is made. Eating leftovers later
must not deduct them again.

- Show portions and deductions before confirmation.
- Store an immutable snapshot of actual ingredient deductions in a cooking event.
- Apply deductions and create the event in one database transaction.
- Protect against repeated submissions; undo each event at most once.
- Undo from its snapshot, not from the recipe's current editable contents.
- Decide how to handle insufficient tracked stock and pre-existing negative stock.

**Acceptance:** double taps do not double-consume stock; recipe edits after cooking
do not alter undo; a failure leaves neither a partial deduction nor a partial event.

## Phase 4: shopping and spending

Retain useful shopping-list behavior, then distinguish desired items from actual
purchases. Today a purchased flag is not a spending record.

- Add purchase quantity, unit, price, currency, store/date as appropriate.
- Preserve purchase history separately from clearing checklist items.
- Compare unit prices only between compatible units and pack quantities.
- Revisit repeated “add recipe” and purchase-toggle semantics so accidental repeats
  cannot silently inflate planned purchases or stock.

**Acceptance:** explain what was spent and what reached stock; clearing a checklist
does not erase spending history; no fabricated cost savings.

## Phase 5: optional nutrition

Only revisit calories/macros after the pantry/cooking workflow is useful. Prefer
manual optional values first. API imports are optional enhancements with clear
source, unit and missing-data behavior, not requirements for ingredient entry.

Before restoring regular meal logging, separate consumption from cooking and
resolve the legacy deduction/undo limitations in the architecture notes.

## Decisions before larger changes

1. Does either previous app contain valuable data that must be imported or retained?
2. Is stock shared across the household, while recipe ratings or eating logs may differ?
3. Which ingredients need exact quantities versus a rough “on hand” indication?

Make migrations only after answering the data question and testing a backup copy.
Use small reviewable branches with regression tests rather than a wholesale rewrite.
