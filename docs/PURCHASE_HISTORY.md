# Shopping and cost history

Stack: pantry/cookability PR #3 → cooking PR #4 → this purchase-history draft.
Review and merge in that order later; nothing is deployed by these branches.

Shop → Record purchase and add stock (on a list row), or Purchases and costs →
Record purchase. Enter date, store, explicit three-letter currency, ingredient,
quantity/unit and **actual total price of each line**, including allocated tax
and discounts. The form accepts up to five lines; unused lines stay blank.
Supported units are g/kg, ml/l and count aliases. No density or package-size
inference, FX conversion, receipt scanning or nutrition is involved.

Saving explicitly adds purchased quantities once, in the same transaction as
immutable receipt snapshots. A stable form token makes retries/double taps safe;
the first successful submission wins, even if a retry changes fields. A fresh
manual form represents a new purchase: this is not receipt deduplication, so do
not manually re-enter an already recorded receipt. Linked shopping rows cannot
be stocked again under another token. Row creation identity prevents old forms
from targeting a newly created SQLite row that reused a cleared integer ID.

Prices remain decimal strings in line snapshots, with up to four decimal places;
receipt totals also use decimal strings to avoid SQLite floating-point money rounding. Free/zero-price lines are explicit. History
shows recorded, voided and net totals separately per entered currency. Codes are
user-entered three-letter labels, not validated against an external currency API.
Comparisons group the same ingredient lifetime, equivalent base unit and currency.
Unit prices are displayed to six decimals; no mass/volume or currency mixing.
Names and prices survive later ingredient edits and deletion of shopping rows.

Void is only for an erroneous entry, not real-world refunds/returns. It appends
an immutable reversal and subtracts the original quantities from current stock.
Later additions/cooks are preserved. Insufficient remaining stock, corrections,
deletions or unit changes block reversal with no partial changes. Voided records
remain visible and excluded from net totals/comparisons. Repeating void or the
original purchase submission never repeats the stock action. Linked list rows
remain completed after void; create a new shopping row for a new purchase.
Unknown pantry totals stay unknown on both purchase and void.

## Historical shopping compatibility

All old shopping rows, quantities, units and purchased flags remain stored and
readable. Already-purchased rows cannot be re-recorded through a linked form.
There are no invented historical costs. The old UI toggle POST now opens manual
purchase entry; old PUT /api/shopping-list/<id>/toggle-purchased returns 409 with
a purchase URL and explanation. This intentional API behavior change prevents
retry-driven additions, negative stock and reversals without price history.
The old helper also refuses stock toggles. Clearing/deleting shopping rows still
works and does not delete purchase history or change stock. There is no automatic
undo of old checkbox purchases whose original movements cannot be proven; use
an explicit pantry correction after reviewing the old data.

## Backup, schema and retest

Adds purchase_receipts, purchase_links and purchase_voids; changes no old columns.
Follow docs/COOK_EVENTS.md backup/restore guidance. create_all only creates missing
tables and does not migrate arbitrary obsolete schemas. Test a restored copy in
a separate database before using existing data. Do not run an old app version
against the same DB while using this branch. No real database was inspected.

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q app scripts tests
PYTHONPATH=. .venv/bin/python scripts/demo_cooking.py
```

The demo uses a new temporary SQLite DB regardless of DATABASE_URL. Visit
http://127.0.0.1:5057/shopping-list; add 200 g Rice (demo), record 0.2 kg at GBP
2.45 from Demo shop. Verify rice 500 → 700 g and 0.012250 GBP/g. A second purchase
of 200 g at GBP 2.00 shows 0.010000 GBP/g and total GBP 4.4500. Void that second
entry: stock returns to 700 g; gross remains 4.4500, voided 2.0000, net 2.4500.
Stop the demo with Ctrl-C. All data is disposable.

## Verification and limits

83 tests pass, including cooking regressions, older stock/recipe/shopping flows,
price immutability, compatible units/currencies, repeat purchase/void, concurrent
purchase/cook and linked submissions, unknown stock, shortage/correction refusal,
shopping-ID reuse and an additive upgrade simulation retaining PR #3-era data.
Production configuration and independent sessions use temporary file-backed
SQLite. Compileall and git diff --check pass. PostgreSQL path is inherited but
not integration-tested here; no PostgreSQL server is available. The existing Pantry regression tests CI runs on Python 3.11 and 3.12.

Actual Chromium QA: narrow 455 CSS-pixel linked purchase entry, 500 → 700 g
inventory, a second 200 g purchase, comparable prices; desktop history, explicit
void warning, void and retained price history/net totals with 700 g stock.
Physical phone/iPhone Safari and touch input are untested. Demo servers stopped.
Prototype authentication, CSRF, default secret and deployment limitations remain;
see README. Shared pantry and personal recipe ratings stay unchanged.
