#!/usr/bin/env python3
"""Read-only schema check. Does not import the app, read rows, or alter the database."""
import argparse
import sqlite3
from pathlib import Path


def inspect_schema(path):
    path = Path(path).expanduser().resolve(strict=True)
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as connection:
        columns = {
            table: {row[1]: row for row in connection.execute(f'PRAGMA table_info({table})')}
            for table in ('ingredients', 'inventory_items')
        }
    warnings = []
    if not columns['ingredients'] or not columns['inventory_items']:
        warnings.append('Expected food-app tables are missing; verify the selected database file.')
    if columns['ingredients'] and 'low_stock_threshold' not in columns['ingredients']:
        warnings.append('ingredients.low_stock_threshold is missing (added in historical commit 952df16).')
    for name in ('low_stock_threshold', 'profile_id'):
        row = columns['inventory_items'].get(name)
        if row and row[3] and row[4] is None:
            warnings.append(f'inventory_items.{name} is a legacy NOT NULL column without a database default; stock inserts can fail.')
    return warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', help='Path to an existing SQLite database, not a SQLAlchemy URL')
    args = parser.parse_args()
    try:
        warnings = inspect_schema(args.database)
    except (OSError, sqlite3.Error) as error:
        parser.exit(2, f'Unable to inspect database: {error}\n')
    for warning in warnings:
        print('WARNING:', warning)
    if not warnings:
        print('No known historical ingredient/inventory schema issues found. This is not a full database validation.')
    else:
        print('No changes made. Back up the database and review a migration before changing its schema.')
    return 1 if warnings else 0


if __name__ == '__main__':
    raise SystemExit(main())
