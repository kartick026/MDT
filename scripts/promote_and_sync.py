from core.store import get_store
import json

store = get_store()
with store.connection(write=True) as db:
    # 1. Promote ayushbajajbusiness to admin
    row = db.execute("SELECT payload FROM records WHERE kind='account' AND id='ayushbajajbusiness'").fetchone()
    if row:
        acct = json.loads(row['payload'])
        acct['role'] = 'admin'
        db.execute("UPDATE records SET payload=? WHERE kind='account' AND id='ayushbajajbusiness'", (json.dumps(acct),))
        print("ayushbajajbusiness is now admin!")

    # 2. Update projects, snapshots, jobs to owner='ayushbajajbusiness' so they appear in their dashboard
    db.execute("UPDATE records SET owner='ayushbajajbusiness' WHERE kind IN ('project', 'snapshot')")
    db.execute("UPDATE jobs SET owner='ayushbajajbusiness'")
    print("Transferred ownership of project and jobs to ayushbajajbusiness!")

print("All updates successful!")
