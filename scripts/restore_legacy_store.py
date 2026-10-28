"""Append a legacy SQLite store to the active store, without overwrites/deletes.

Run with PYTHONPATH=backend python scripts/restore_legacy_store.py SOURCE
for a dry run; add --apply to commit the transaction. Back up both stores first.
Conflicting saved content aborts the entire transaction. The source is read-only.
"""
import argparse
import json
from pathlib import Path
import sqlite3


def read_legacy(path):
    path = Path(path).resolve(strict=True)
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        data = {table: [dict(row) for row in db.execute('SELECT * FROM ' + table)] for table in ['records', 'jobs']}
    if any(row['status'] in {'queued', 'running'} for row in data['jobs']):
        raise ValueError('Source contains unfinished work; resolve it before recovery to avoid replaying jobs.')
    return data


def restore_legacy(path, store, apply=False):
    data = read_legacy(path)
    pending, unchanged = {'records': [], 'jobs': []}, {'records': 0, 'jobs': 0}
    with store.connection(write=True) as db:
        if store.postgres:
            db.execute('LOCK TABLE records, jobs IN SHARE ROW EXCLUSIVE MODE')
        for table, rows in data.items():
            for row in rows:
                if table == 'records':
                    previous = db.execute('SELECT * FROM records WHERE kind=? AND id=?', (row['kind'], row['id'])).fetchone()
                else:
                    previous = db.execute('SELECT * FROM jobs WHERE id=?', (row['id'],)).fetchone()
                if previous:
                    before, after = dict(previous), dict(row)
                    if table == 'records':
                        # Preserve the target's timestamps for identical records.
                        before.pop('created'); after.pop('created')
                        before['payload'] = json.loads(before['payload'])
                        after['payload'] = json.loads(after['payload'])
                    if before != after:
                        raise ValueError(f'Conflicting {table} record {row["id"]}; target was not overwritten.')
                    unchanged[table] += 1
                else:
                    pending[table].append(row)
        if apply:
            for table, rows in pending.items():
                for row in rows:
                    # Columns come from the fixed app schema, never user input.
                    allowed = {'records': {'kind','id','owner','project','payload','created'},
                               'jobs': {'id','owner','project','status','stage','payload','result','error','created','updated','lease','expires','attempts','dedupe'}}[table]
                    if set(row) != allowed:
                        raise ValueError('Unexpected legacy schema; no records were changed.')
                    columns = list(row)
                    db.execute(f'INSERT INTO {table} ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})', tuple(row[key] for key in columns))
    return {'applied': apply, 'added': {table: len(rows) for table, rows in pending.items()}, 'unchanged': unchanged}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    from core.store import get_store
    print(json.dumps(restore_legacy(args.source, get_store(), args.apply)))
