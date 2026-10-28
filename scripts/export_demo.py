"""Recompute the bundled public example without reading local credentials/data.

Run with the backend dependencies installed. --check fails when the checked-in
asset differs from the current detector, fixture or measured previews.
"""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / 'frontend' / 'public' / 'demo.json'
    with tempfile.TemporaryDirectory(prefix='mdt-demo-') as directory:
        target = Path(directory)
        shutil.copytree(root / 'backend', target / 'backend', ignore=shutil.ignore_patterns(
            '.env', '.env.*', 'data', '__pycache__', '*.pyc', 'chroma_db'))
        # Preserve only runtime/OS variables. Do not inherit engine overrides,
        # credentials, local repository paths or user-specific demo settings.
        env = {key: value for key, value in os.environ.items() if key.upper() in {
            'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'LANG', 'LC_ALL', 'PYTHONHOME'}}
        env.update(TESTING='true', ENVIRONMENT='test', RUNTIME_PROFILE='local',
                   OPENAI_API_KEY='', GITHUB_TOKEN='', GITHUB_APP_ID='', GITHUB_APP_PRIVATE_KEY='',
                   DATABASE_URL=str(target / 'demo.sqlite3'), NEO4J_URI='bolt://127.0.0.1:1',
                   PYTHONPATH=str(target / 'backend'), PYTHONIOENCODING='utf-8')
        generated = target / 'demo.json'
        subprocess.run([sys.executable, '-c',
            'import json,sys; from pathlib import Path; from api.projects import public_demo; '
            'Path(sys.argv[1]).write_text(json.dumps(public_demo(), ensure_ascii=False, separators=(",", ":"))+"\\n", encoding="utf-8")',
            str(generated)], cwd=target, env=env, check=True)
        payload = generated.read_text(encoding='utf-8')
        if args.check:
            if not output.exists() or json.loads(output.read_text(encoding='utf-8')) != json.loads(payload):
                raise SystemExit('Bundled demo is stale. Run python scripts/export_demo.py, then rebuild the frontend.')
            print('Bundled demo matches the current detector, fixture and recomputed previews.')
        else:
            output.write_text(payload, encoding='utf-8')
            print(f'Updated {output.relative_to(root)} from canonical fixture calculations.')


if __name__ == '__main__':
    main()
