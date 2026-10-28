import sqlite3
import json

conn = sqlite3.connect('/app/data/mdt.sqlite3')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

for row in cursor.execute("SELECT id, kind, payload FROM records WHERE kind IN ('snapshot', 'project') LIMIT 5").fetchall():
    data = json.loads(row['payload'])
    deps = data.get('dependencies') or data.get('snapshot', {}).get('dependencies') or []
    print(f"Record {row['kind']} {row['id']}: found {len(deps)} dependencies")
    for d in deps[:10]:
        print("  ", d)
