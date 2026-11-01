"""Risk regressions exercise the full scoring path, not just path classifiers."""
import pytest
from core.registry import RegistryManager
from services.git_analyzer import GitAnalyzer
from services.impact_engine import ImpactEngine
from services.analysis_evidence import assess_evidence


def snapshot(read=2, candidates=2):
    return {"services": [{"name": name} for name in ("backend", "web", "worker")],
            "dependencies": [{"from": "web", "to": "backend"}, {"from": "worker", "to": "backend"}],
            "file_mappings": {"app": "backend"},
            "coverage": {"per_service": {"backend": read}, "per_service_candidates": {"backend": candidates}}}


def change(old, new, path="app/api.py", **kwargs):
    return GitAnalyzer()._build_change(path, "modified", old, new, **kwargs)


@pytest.mark.asyncio
async def test_equivalent_core_service_changes_have_zero_risk_even_at_depth():
    code = "@app.get('/items')\ndef items():\n    return []\n"
    with RegistryManager.use_snapshot(snapshot(), "risk-regression"):
        result = await ImpactEngine().analyze_impact([change(code, code + "# comment\n")])
        assert result.risk_score == 0
        assert result.impacted_services == []
        assert result.assessment_status == "no_semantic_change"
        assert result.confidence_evidence["equivalent_files"] == 1


@pytest.mark.asyncio
async def test_breaking_route_scores_above_additive_route():
    code = "@app.get('/items')\ndef items():\n    return []\n"
    with RegistryManager.use_snapshot(snapshot(), "risk-regression"):
        engine = ImpactEngine()
        additive = await engine.analyze_impact([change(code, code + "@app.get('/health')\ndef health():\n    return True\n")])
        breaking = await engine.analyze_impact([change(code, code.replace('/items', '/products'))])
        assert breaking.risk_score > additive.risk_score > 0


def test_confidence_tracks_missing_source_and_mapping_not_graph_depth():
    item = change("value = 1\n", "value = 2\n")
    with RegistryManager.use_snapshot(snapshot(), "risk-regression"):
        value, status, evidence = assess_evidence([item], snapshot())
        assert value == 1 and status == "supported"
        assert evidence["calibrated"] is False
        assert assess_evidence([item], snapshot(1))[0] == 0.5
        assert assess_evidence([item], snapshot(0))[:2] == (0, "insufficient_evidence")
        unmapped = change("value = 1\n", "value = 2\n", "other/api.py")
        assert assess_evidence([unmapped], snapshot())[:2] == (0, "insufficient_evidence")
        missing = change("", "", warnings=["old_source_unavailable", "new_source_unavailable"])
        assert assess_evidence([missing], snapshot())[:2] == (0, "insufficient_evidence")


@pytest.mark.asyncio
async def test_partial_source_cannot_look_like_confirmed_safe_noop():
    with RegistryManager.use_snapshot(snapshot(), "risk-regression"):
        item = change("", "", warnings=["old_source_unavailable", "new_source_unavailable"])
        result = await ImpactEngine().analyze_impact([item])
        assert result.assessment_status == "insufficient_evidence"
        assert result.confidence == 0
        assert "provisional" in result.explanation
