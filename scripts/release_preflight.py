"""Read-only public-release checklist. Never uploads, publishes or reads secrets.

Copy release-config.example.json to release-config.local.json, fill decided
metadata, and mark acceptance checks only after they have actually been run.
Exit 2 means release is not ready; local review packages can still be built.
"""
import argparse
import ipaddress
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit


def public_https(value):
    if not isinstance(value, str):
        return False
    try:
        url = urlsplit(value or '')
        host = (url.hostname or '').lower()
        if url.scheme != 'https' or not host or url.username or url.password:
            return False
        if host == 'localhost' or host.endswith(('.localhost', '.test', '.invalid', '.example')) or host in {'example.com', 'example.org', 'example.net'}:
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return '.' in host
    except ValueError:
        return False


def check(config):
    missing = []
    for field in ('web_url', 'api_url', 'privacy_url'):
        if not public_https(config.get(field)):
            missing.append(field + ': supply the actual public HTTPS URL')
    publisher = config.get('publisher_id')
    if not isinstance(publisher, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{2,}', publisher) or publisher == 'mdt-local-alpha':
        missing.append('publisher_id: supply the registered publisher identity')
    if not isinstance(config.get('support_contact'), str) or not config['support_contact'].strip():
        missing.append('support_contact: supply the agreed support address or URL')
    if not isinstance(config.get('license_spdx'), str) or not config['license_spdx'].strip() or config['license_spdx'] == 'UNLICENSED':
        missing.append('license_spdx: select a contributor-approved license')
    for field in ('contributors_approved_license', 'public_https_cors_verified',
                  'hosted_restart_restore_verified', 'chrome_edge_permission_workflows_verified',
                  'vscode_restricted_mode_verified', 'vscode_native_upload_consent_verified', 'deployed_vscode_dev_verified',
                  'container_findings_reviewed'):
        if config.get(field) is not True:
            missing.append(field + ': acceptance evidence is still required')
    return missing


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(__file__).resolve().parents[1] / 'release-config.example.json')
    parser.add_argument('--profile', choices=('alpha', 'professional'), default='alpha')
    parser.add_argument('--evidence', type=Path, default=Path(__file__).resolve().parents[1] / 'release-evidence.example.json')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8-sig'))
    missing = check(config)
    if args.profile == 'professional':
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from scripts.professional_readiness import check_professional
        evidence_result = check_professional(json.loads(args.evidence.read_text(encoding='utf-8-sig')), config)
        missing.extend(gate['gate'] + ': ' + reason for gate in evidence_result['gates'] for reason in gate['remaining'])
    print(json.dumps({'ready_to_publish': not missing, 'remaining': missing,
                      'profile': args.profile,
                      'scope': 'Metadata and recorded acceptance only; no network verification or publication'}, indent=2))
    raise SystemExit(2 if missing else 0)
