"""
End-to-end verification script for Neon PostgreSQL integration.
Tests durable storage operations against the Neon database:
1. Verifies connection to Neon PostgreSQL
2. Reads current database, user, and schema
3. Writes a project record
4. Enqueues a job
5. Retrieves the record and job
6. Cleans up test data
"""
import uuid
import time
from core.store import get_store

def run_e2e_test():
    print("=== Testing Neon PostgreSQL Store End-to-End ===")
    store = get_store()
    print(f"Store backend: {'PostgreSQL (Neon)' if store.postgres else 'SQLite'}")
    assert store.postgres, "Store is not using PostgreSQL!"

    # 1. Connection and schema check
    with store.connection() as db:
        row = db.execute("SELECT current_database() AS db, current_user AS usr, current_schema() AS schema;").fetchone()
        print(f"Connected to Neon DB: '{row['db']}', User: '{row['usr']}', Schema: '{row['schema']}'")

    # 2. Write test record
    test_id = f"test-{uuid.uuid4().hex[:8]}"
    owner = "e2e-tester"
    project = "neon-integration-project"
    payload = {"status": "ok", "timestamp": time.time(), "neon": True}

    print(f"\n1. Writing test record to Neon ({test_id})...")
    store.put("test_record", test_id, owner, payload, project=project)
    print("   -> Record written successfully!")

    # 3. Read test record back
    print("2. Reading test record back from Neon...")
    fetched = store.get("test_record", test_id, owner)
    assert fetched is not None, "Failed to retrieve written record!"
    assert fetched.get("neon") is True, f"Payload mismatch: {fetched}"
    print(f"   -> Record retrieved verified: {fetched}")

    # 4. Enqueue and query job
    print("\n3. Testing Job Queue in Neon...")
    job_id = store.enqueue(owner, project, {"task": "verify_neon"}, dedupe=f"dedupe-{test_id}")
    print(f"   -> Enqueued job ID: {job_id}")

    job = store.job(job_id, owner)
    assert job is not None, "Failed to retrieve enqueued job!"
    print(f"   -> Job status: {job['status']}, stage: {job['stage']}")

    # 5. Clean up test data
    print("\n4. Cleaning up test record and job...")
    with store.connection(write=True) as db:
        db.execute("DELETE FROM records WHERE kind = %s AND id = %s", ("test_record", test_id))
        db.execute("DELETE FROM jobs WHERE id = %s", (job_id,))
    print("   -> Cleanup completed.")

    print("\n[SUCCESS] Neon PostgreSQL store verified end-to-end!")

if __name__ == "__main__":
    run_e2e_test()
