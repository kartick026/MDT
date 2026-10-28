import sqlite3
import json
import os
import glob

possible_paths = [
    'backend/data/mdt.sqlite3',
    '/app/data/mdt.sqlite3',
    'data/mdt.sqlite3',
    '/data/mdt.sqlite3'
]

db_files = []
for p in possible_paths:
    if os.path.exists(p):
        db_files.append(p)

for f in glob.glob("/app/data/*") + glob.glob("backend/data/*"):
    if f not in db_files:
        db_files.append(f)

print("Found files:", db_files)

for db_path in db_files:
    if not (db_path.endswith('.sqlite3') or db_path.endswith('.db')):
        continue
    print(f"\n=================== Checking {db_path} ===================")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=== TABLES ===")
    for t in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        print(t['name'])

    print("\n=== RECORDS ===")
    for r in cursor.execute("SELECT kind, id, owner, project, payload, created FROM records").fetchall():
        try:
            p = json.loads(r['payload'])
            repo = p.get('repo_url') or p.get('repository') or p.get('name')
        except Exception as e:
            p = str(e)
            repo = 'unknown'
        print(f"kind={r['kind']}, id={r['id']}, owner={r['owner']}, project={r['project']}, repo={repo}")
        if r['kind'] == 'project':
            print(f"   Project Details: name={p.get('name')}, repo_url={p.get('repo_url')}, branch={p.get('branch')}")
        elif r['kind'] == 'legacy_analysis':
            print(f"   Legacy Analysis: repo={p.get('repo_url')}, service={p.get('service')}, risk={p.get('risk_score')}")

    print("\n=== JOBS ===")
    for j in cursor.execute("SELECT id, owner, project, status, stage, payload, created FROM jobs").fetchall():
        try:
            p = json.loads(j['payload'])
        except Exception as e:
            p = str(e)
        print(f"job_id={j['id']}, owner={j['owner']}, project={j['project']}, status={j['status']}, stage={j['stage']}")
        print(f"   Job Payload: {p}")
