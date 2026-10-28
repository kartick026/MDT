from fastapi.testclient import TestClient

from app import app
from core.auth import create_access_token
from domain.policies import evaluate_policies, policy_version


def test_constraints_preserve_explicit_unresolved_evidence_and_scores():
    snapshot = {"services": [{"name": "a"}, {"name": "b"}], "dependencies": [{"from": "a", "to": "b"}]}
    rules = [{"kind": "forbid", "source": "a", "target": "b", "reason": "Separate storage boundary"},
             {"kind": "require", "source": "b", "target": "a", "reason": "Required dependency"},
             {"kind": "require", "source": "a", "target": "missing", "reason": "Unknown target"}]
    result = evaluate_policies(snapshot, rules)
    assert result["violations"] == 2 and result["unresolved"] == 1
    assert result["score_effect"] == "none" and result["scope"] == "captured_topology"
    assert result["version"] == policy_version(rules)
    assert "status" not in rules[0]
    rules[0]["kind"] = "require"
    assert evaluate_policies(snapshot, rules)["rules"][0]["status"] == "satisfied"


def test_project_rules_owned_validated_and_copied_into_job(isolate_durable_store):
    store = isolate_durable_store
    store.create_project("admin", {"id": "policy-project", "name": "Policies", "ready": True,
        "snapshot_version": "v1", "snapshot": {"services": [{"name": "a"}], "dependencies": []}})
    store.put("account", "other", "auth", {"role": "analyst", "is_active": True})
    def headers(owner="admin"):
        return {"Authorization": "Bearer " + create_access_token({"sub": owner, "role": "admin"})}
    client, path = TestClient(app), "/v1/projects/policy-project/policies"
    rules = [{"kind": "forbid", "source": "a", "target": "b", "reason": "Boundary rule"}]
    assert client.put(path, headers=headers("other"), json={"rules": rules}).status_code == 404
    assert client.get(path).status_code == 401
    assert client.put(path, headers=headers(), json={"rules": rules * 2}).status_code == 422
    assert client.put(path, headers=headers(), json={"rules": [{**rules[0], "reason": "  "}]}).status_code == 422
    saved = client.put(path, headers=headers(), json={"rules": rules})
    assert saved.status_code == 200 and saved.json()["evaluation"]["unresolved"] == 1
    assert client.get(path, headers=headers()).json()["rules"] == rules
    assert client.post("/v1/projects/policy-project/analyses", headers=headers(), json={"source": "commit", "head_ref": "main"}).status_code == 202
    queued = store.claim()
    assert queued["payload"]["policy"]["rules"] == rules
    client.put(path, headers=headers(), json={"rules": []})
    assert queued["payload"]["policy"]["rules"] == rules
    store.delete_project("policy-project", "admin")
    assert store.get("policy", "policy-project", "admin") is None
