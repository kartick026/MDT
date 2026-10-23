import copy

from fastapi.testclient import TestClient
from app import app
from api.projects import _demo_snapshot
from core.registry import RegistryManager
from domain.architecture import GraphSnapshot, configured_thresholds, detect_smells
from services.remediation_simulator import GraphEdit, apply_snapshot_edits, breakdown_smells, compute_architecture_health


def test_public_demo_previews_are_recomputed_from_exact_edits_without_mutation():
    original = copy.deepcopy(RegistryManager.load())
    data = TestClient(app).get('/v1/demo').json()
    snapshot = GraphSnapshot.from_data(_demo_snapshot())
    assert len(data['suggested_fixes']) == 3
    for fix in data['suggested_fixes']:
        preview = fix['recorded_preview']
        after, _ = apply_snapshot_edits(snapshot, [GraphEdit(**edit) for edit in fix['edits']])
        health = compute_architecture_health(breakdown_smells(detect_smells(after, configured_thresholds())), after)
        assert preview['snapshot_version'] == data['snapshot_version'] == snapshot.version
        assert preview['before']['score'] == data['architecture_smell_score']
        assert preview['after'] == health
        assert preview['preview_snapshot_version'] == after.version
        assert preview['provenance']['baseline'] == 'server_recomputed'
        assert all(ident in {f['id'] for f in data['smells']} for ident in fix['finding_ids'])
        assert 'mockPreview' not in fix
    assert RegistryManager.load() == original
