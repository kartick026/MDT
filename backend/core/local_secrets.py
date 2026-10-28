"""Persist a local signing key across processes and container recreations."""
import os
from pathlib import Path
import secrets
import tempfile


def local_signing_key(filename: str) -> str:
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        descriptor, temporary = tempfile.mkstemp(prefix='.jwt-', dir=path.parent)
        try:
            with os.fdopen(descriptor, 'w', encoding='ascii') as stream:
                stream.write(secrets.token_urlsafe(48))
                stream.flush()
                os.fsync(stream.fileno())
            try:
                # Publish the complete key atomically; concurrent starters use the winner.
                os.link(temporary, path)
            except FileExistsError:
                pass
        finally:
            os.unlink(temporary)
    key = path.read_text(encoding='ascii').strip()
    if len(key) < 32:
        raise ValueError('The persisted local JWT key is invalid; restore it from backup rather than rotating it automatically.')
    return key
