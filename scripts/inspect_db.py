from core.store import get_store
import json

store = get_store()
with store.connection() as db:
    records = db.execute("SELECT kind, id, owner, project, payload FROM records").fetchall()
    print("Total records:", len(records))
    for r in records:
        print(f"[{r['kind']}] id={r['id']} owner={r['owner']} project={r['project']}")
        if r['kind'] == 'project':
            data = json.loads(r['payload'])
            print(f"   Project Name: {data.get('name')} | Repo: {data.get('repo_url')}")
    
    jobs = db.execute("SELECT id, owner, project, status, stage, payload FROM jobs").fetchall()
    print("\nTotal jobs:", len(jobs))
    for j in jobs:
        print(f"[job] id={j['id']} owner={j['owner']} status={j['status']}")
        try:
            data = json.loads(j['payload'])
            print(f"   Job Repo: {data.get('repo_url')}")
        except Exception:
            pass
