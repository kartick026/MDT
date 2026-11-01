"""Common utility functions for MDT backend."""
import time
from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, List


def now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


_rate_limit_records: Dict[str, List[float]] = defaultdict(list)
_rate_limit_lock = Lock()


def check_rate_limit(
    client_ip: str,
    max_requests: int = 30,
    window_seconds: int = 60,
    scope: str = "default",
) -> bool:
    """Return True if allowed, False if rate limit exceeded in the time window.
    
    Scoped per feature (e.g. 'login', 'webhook') to prevent cross-endpoint starvation.
    Atomic across threads in this process. Multiple API processes require a
    shared edge limiter; this local guard does not enforce a fleet-wide quota.
    """
    now = time.time()
    key = f"{scope}:{client_ip}"

    with _rate_limit_lock:
        # Prune stale records if tracking dictionary grows large.
        if len(_rate_limit_records) > 1000:
            stale_keys = [k for k, ts in _rate_limit_records.items() if not ts or (now - ts[-1] > window_seconds * 2)]
            for k in stale_keys:
                _rate_limit_records.pop(k, None)

        timestamps = _rate_limit_records[key]
        valid = [t for t in timestamps if now - t < window_seconds]
        _rate_limit_records[key] = valid
        if len(valid) >= max_requests:
            return False
        valid.append(now)
        return True


def reset_rate_limit_records() -> None:
    """Reset rate-limiting tracker (primarily used in tests)."""
    with _rate_limit_lock:
        _rate_limit_records.clear()
