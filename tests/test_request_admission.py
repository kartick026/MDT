"""Adversarial admission checks; no live accounts or source uploads."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import time

import pytest
from pydantic import ValidationError

from core import utils
from api.projects import AnalysisInput


def test_simultaneous_login_attempts_cannot_lose_rate_limit_counts(monkeypatch):
    class SlowRead(list):
        def __iter__(self):
            # Force preemption after reading the shared bucket. Previously each
            # thread replaced it with its own list and every request was allowed.
            time.sleep(0.03)
            return super().__iter__()

    monkeypatch.setitem(utils._rate_limit_records, "login:race-client", SlowRead())
    start = Barrier(12)

    def attempt(_):
        start.wait(timeout=5)
        return utils.check_rate_limit("race-client", max_requests=3, scope="login")

    with ThreadPoolExecutor(max_workers=12) as pool:
        allowed = list(pool.map(attempt, range(12)))
    assert sum(allowed) == 3


@pytest.mark.parametrize("extra", [
    {"before_files": {}, "after_files": {"a.py": "different source"}},
    {"before_files": {"a.py": "hidden context"}},
    {"after_files": {}},
])
def test_source_representations_cannot_silently_override_each_other(extra):
    with pytest.raises(ValidationError, match="one source representation"):
        AnalysisInput(source="patch", base_ref="HEAD", local_changes=[{
            "file_path": "a.py", "old_content": "", "new_content": "x = 1\n",
        }], **extra)
