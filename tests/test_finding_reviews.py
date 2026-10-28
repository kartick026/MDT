import copy
import time

import pytest
from fastapi.testclient import TestClient

from app import app
from core.auth import create_access_token
from domain.architecture import GraphSnapshot


def headers(owner="admin"):
    return {"Authorization": "Bearer " + create_access_token({"sub": owner, "role": "admin"})}


@pytest.fixture
def saved(isolate_durable_store):
    store = isolate_durable_store
    snapshot = {"services": [{"name": "api"}], "dependencies": []}
    project = {"id": "review-project", "name": "Reviews", "ready": True, "repo_url": "https://github.com/test/repo",
               "snapshot": snapshot, "snapshot_version": GraphSnapshot.from_data(snapshot).version}
    store.create_project("admin", project)
    ident = store.enqueue("admin", project["id"], {}, require_project=True)
    job = store.claim()
    result = {"kind": "analysis", "smells": [{"id": "finding-1", "type": "CYCLE"}], "risk_score": 75,
              "architecture_smell_score": 43.125, "_snapshot": snapshot, "snapshot_version": project["snapshot_version"]}
    store.finish(job, result)
    return store, ident, copy.deepcopy(result)


def test_reviews_are_owned_expiring_annotations_without_score_mutation(saved):
    store, ident, original = saved
    client = TestClient(app)
    path = f"/v1/analyses/{ident}/reviews"
    assert client.get(path).status_code == 401
    store.put("account", "other", "auth", {"role": "analyst", "is_active": True})
    assert client.get(path, headers=headers("other")).status_code == 404
    body = {"classification": "accepted_risk", "reason": "Reviewed academic fixture", "expires_days": 7}
    assert client.put(path + "/finding-1", headers=headers("other"), json=body).status_code == 404
    assert client.put(path + "/unknown", headers=headers(), json=body).status_code == 404
    response = client.put(path + "/finding-1", headers=headers(), json=body)
    assert response.status_code == 200
    review = response.json()
    assert review["score_effect"] == "none" and review["expired"] is False
    assert 6.9 * 86400 < review["expires_at"] - time.time() < 7.1 * 86400
    assert store.job(ident, "admin")["result"] == original
    review["expires_at"] = time.time() - 1
    store.put_project_record("finding_review:" + ident, ident + ":finding-1", "admin", "review-project", review)
    assert client.get(path, headers=headers()).json()["reviews"][0]["expired"]
    store.delete_project("review-project", "admin")
    assert client.get(path, headers=headers()).status_code == 404
    assert not store.list("finding_review:" + ident, "admin")


@pytest.mark.parametrize("override", [{"reason": "   "}, {"expires_days": 0}, {"expires_days": 91}, {"classification": "safe"}])
def test_review_validation(saved, override):
    _, ident, _ = saved
    response = TestClient(app).put(f"/v1/analyses/{ident}/reviews/finding-1", headers=headers(),
                                  json={"classification": "confirmed", "reason": "Source verified", **override})
    assert response.status_code == 422
