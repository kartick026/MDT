"""Append a legacy SQLite store to the active store, without overwrites/deletes.

Run with python scripts/restore_legacy_store.py SOURCE
for a dry run; add --apply to commit the transaction. Back up both stores first.
Conflicting saved content aborts the entire transaction. The source is read-only.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts._runtime import add_backend_path, ensure_runtime
from scripts._database import ReadonlyStore, configured_database_url, diagnostic_main


def read_legacy(path):
    path = Path(path).resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        data = {table: [dict(row) for row in db.execute('SELECT * FROM ' + table)] for table in ['records', 'jobs']}
    if any(row['status'] in {'queued', 'running'} for row in data['jobs']):
        raise ValueError('Source contains unfinished work; resolve it before recovery to avoid replaying jobs.')
    return data


def restore_legacy(path, store, apply=False):
    data = read_legacy(path)
    pending, unchanged = {'records': [], 'jobs': []}, {'records': 0, 'jobs': 0}
    with store.connection(write=apply) as db:
        if store.postgres and apply:
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    ensure_runtime(('dotenv', 'psycopg', 'pydantic_settings'))
    url = configured_database_url()
    if args.apply:
        add_backend_path()
        from core.store import Store
        store = Store(url)
    else:
        store = ReadonlyStore(url)
    print(json.dumps(restore_legacy(args.source, store, args.apply)))


if __name__ == '__main__':
    raise SystemExit(diagnostic_main(main))
