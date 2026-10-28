import sqlite3
import json

conn = sqlite3.connect('/app/data/mdt.sqlite3')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("=== PROJECTS IN PREVIOUS SQLITE HISTORY ===")
for r in cursor.execute("SELECT id, owner, payload, created FROM records WHERE kind='project' ORDER BY created DESC").fetchall():
    p = json.loads(r['payload'])
    print(f"- Project ID: {r['id']}")
    print(f"  Owner:      {r['owner']}")
    print(f"  Name:       {p.get('name')}")
    print(f"  Repo URL:   {p.get('repo_url')}")
    print(f"  Branch:     {p.get('branch')}")
    print(f"  Created:    {r['created']}")
    print()

print("=== ANALYSES / JOBS IN PREVIOUS SQLITE HISTORY ===")
for j in cursor.execute("SELECT id, owner, project, status, stage, payload, created FROM jobs ORDER BY created DESC").fetchall():
    try:
        p = json.loads(j['payload']) if j['payload'] else {}
    except:
        p = {}
    print(f"- Job ID: {j['id']} | Owner: {j['owner']} | Project ID: {j['project']} | Status: {j['status']} | Stage: {j['stage']}")
    if p:
        print(f"  Source: {p.get('source')} | Base: {p.get('base_ref')} | Head: {p.get('head_ref')}")
