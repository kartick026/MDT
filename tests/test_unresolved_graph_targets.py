"""Unresolved references must survive import, canonical snapshots and graph display."""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import app
from domain.architecture import GraphSnapshot, snapshot_from_transaction
from services.repo_onboarding import RepoOnboarder


@pytest.mark.parametrize('dependency', ['[redis, db]', '{redis: {condition: service_started}, db: {condition: service_healthy}}'])
def test_missing_compose_targets_are_retained_and_distinguished_from_real_services(dependency):
    services, edges, _ = RepoOnboarder()._parse_compose(f'''
services:
  worker:
    image: php:8
    depends_on: {dependency}
  redis-dev:
    image: redis:7
  db-dev:
    image: mysql:8
''', 'docker-compose.yaml')
    nodes = {service['name']: service for service in services}
    assert set(nodes) == {'worker', 'redis-dev', 'db-dev', 'redis', 'db'}
    assert all(nodes[name]['is_broken'] is True and nodes[name]['node_type'] == 'external' for name in ('redis', 'db'))
    assert all(not nodes[name].get('is_broken') for name in ('worker', 'redis-dev', 'db-dev'))
    assert {edge['to'] for edge in edges} == {'redis', 'db'}
    assert all(edge['has_bug'] is True and edge['type'] == 'startup' and edge['source_file'] == 'docker-compose.yaml' for edge in edges)
    raw = {'services': services, 'dependencies': edges}
    snapshot = GraphSnapshot.from_data(raw)
    assert all(edge['has_bug'] is True for edge in snapshot.to_data()['dependencies'])
    assert snapshot.version == GraphSnapshot.from_data(snapshot.to_data()).version


def test_repeated_undefined_target_creates_one_node_and_keeps_each_caller():
    services, edges, _ = RepoOnboarder()._parse_compose('''
services:
  a:
    image: python
    depends_on: [missing]
  b:
    image: python
    depends_on: [missing]
''')
    assert len([node for node in services if node['name'] == 'missing']) == 1
    assert {(edge['from'], edge['to']) for edge in edges} == {('a', 'missing'), ('b', 'missing')}


def test_existing_startup_targets_are_never_marked_broken():
    services, edges, _ = RepoOnboarder()._parse_compose('''
services:
  worker:
    image: php
    depends_on: [redis-dev]
  redis-dev:
    image: redis
''')
    assert not any(service.get('is_broken') for service in services)
    assert not any(edge.get('has_bug') for edge in edges)


def test_public_demo_exposes_one_explicit_broken_target_with_its_call():
    snapshot = TestClient(app).get('/v1/demo').json()['snapshot']
    missing = [node for node in snapshot['services'] if node.get('is_broken')]
    assert [node['name'] for node in missing] == ['inventory-service']
    assert missing[0]['resolution_source'] == 'illustrative_fixture'
    assert 'absent from the demo deployment' in missing[0]['resolution_reason']
    assert any(edge['from'] == 'order-service' and edge['to'] == 'inventory-service' for edge in snapshot['dependencies'])


def test_legacy_projection_preserves_captured_resolution_evidence():
    context = GraphSnapshot.from_data({'services': [{'name': 'missing', 'node_type': 'external', 'is_broken': True,
        'resolution_reason': 'Not declared', 'resolution_source': 'compose.yaml'}], 'dependencies': []})
    tx = MagicMock()
    tx.run.return_value.single.return_value = {'services': [{'name': 'missing', 'node_type': 'external'}], 'dependencies': []}
    assert snapshot_from_transaction(tx, context).version == context.version
