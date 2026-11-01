"""Check Git-managed text for credential literals; output locations, never values.

Use --staged as a pre-commit check. The default scans the tracked working tree.
Environment files are prohibited except explicit example/template files.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]

PATTERNS = {
    'database credential': re.compile(r'(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s"\'<>:/]+:([^\s"\'<>@]+)@'),
    'Neon password': re.compile(r'\bnpg_[A-Za-z0-9]{12,}\b'),
    'GitHub token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b'),
    'Google API key': re.compile(r'\bAIza[0-9A-Za-z_-]{30,}\b'),
    'OpenAI API key': re.compile(r'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{30,}\b'),
}
PRIVATE_KEY = re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----(?:\s|\\n)+[A-Za-z0-9+/=]{32,}')


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str


def environment_file(path: str) -> bool:
    name = Path(path).name
    template = name.endswith(('.env.example', '.env.template'))
    return not template and (name == '.env' or name.startswith('.env.') or name.endswith('.env') or '.env.' in name)


def placeholder(value: str) -> bool:
    return value.lower() in {'password', 'secret', 'pass', 'user', 'postgres', 'ci-disposable-password'} or bool(re.search(r'\$\{|%[A-Z_]+%|<[^>]+>|your[_-]|example|placeholder|changeme|test[_-]|dummy', value, re.I))


def scan_text(path: str, content: str) -> list[Finding]:
    findings = []
    if environment_file(path):
        findings.append(Finding(path, 1, 'environment file must not be tracked'))
    for number, line in enumerate(content.splitlines(), 1):
        for kind, pattern in PATTERNS.items():
            for match in pattern.finditer(line):
                value = match.group(1) if kind == 'database credential' else match.group()
                if not placeholder(value):
                    findings.append(Finding(path, number, kind))
    for match in PRIVATE_KEY.finditer(content):
        findings.append(Finding(path, content.count('\n', 0, match.start()) + 1, 'private key'))
    return findings


def scan_git(staged: bool = False) -> list[Finding]:
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    findings = []
    for name in paths:
        if not name:
            continue
        if staged:
            result = subprocess.run(['git', 'show', ':' + name], cwd=ROOT, capture_output=True)
            if result.returncode:
                continue
            raw = result.stdout
        else:
            path = ROOT / name
            if not path.is_file():
                continue
            raw = path.read_bytes()
        if b'\0' in raw:
            if environment_file(name):
                findings.append(Finding(name, 1, 'environment file must not be tracked'))
            continue
        findings.extend(scan_text(name, raw.decode('utf-8', errors='replace')))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true')
    args = parser.parse_args()
    findings = scan_git(args.staged)
    for finding in findings:
        print(f'{finding.path}:{finding.line}: {finding.kind} [REDACTED]')
    if findings:
        print(f'FAILED: {len(findings)} possible credential exposures. No secret values were printed.')
        return 1
    print('PASS: no credential literals or private environment files found in Git-managed source.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
