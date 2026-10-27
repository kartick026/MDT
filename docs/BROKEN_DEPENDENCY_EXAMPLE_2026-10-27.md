# Broken dependency examples

Verified repository: [SMEWebify/WebErpMesv2](https://github.com/SMEWebify/WebErpMesv2), using historical revision `7595d2abbffcf1f984a6aad1eca48e7630fbf3fc`.

Its [docker-compose.yaml](https://github.com/SMEWebify/WebErpMesv2/blob/7595d2abbffcf1f984a6aad1eca48e7630fbf3fc/docker-compose.yaml#L72-L74) makes `worker` depend on `redis` and `db`. The declared services are named `redis-dev` and `db-dev`. [Issue #1174](https://github.com/SMEWebify/WebErpMesv2/issues/1174) documents the failure, and [the upstream fix](https://github.com/SMEWebify/WebErpMesv2/commit/1a7c8874b2c3f2b508e84a1f7d52e44080afd4ad) corrects the two names. The current project has been fixed; use the pinned revision to reproduce the historical defect.

Expected graph connections:

- `worker → redis`: unresolved startup dependency.
- `worker → db`: unresolved startup dependency.

These are missing declarations in the selected Compose configuration. No runtime outage or network refusal was inferred. A real deployment may use additional Compose overrides; the graph explains the configuration it actually captured.

The importer previously discarded undefined targets. It now keeps an external placeholder node, the startup-order edge, source filename and resolution explanation. The immutable graph retains those fields. Ordinary external resources remain unobserved and are not automatically marked broken.

The public demo uses its existing intentional `order-service → inventory-service` dependency, endpoint `/api/v1/inventory/reserve`. The missing inventory service is an illustrative fixture, absent from the demo deployment. Snapshot creation previously dropped its broken-target flag. The node and incoming connection now retain their red broken-link treatment, and selecting either shows the explanation. No redundant placeholder was added beside that existing target.

Validation: 85 focused backend tests, 33 frontend tests, frontend lint, and a complete import of the pinned public archive. The import produces eight nodes and eight relations, including both unresolved targets and two `UNDEFINED_COMPOSE_SERVICE` connection issues. The downloaded source is read as data; repository code is not executed.

See [the full pinned-source import evidence](benchmarks/broken-dependency-repository-2026-10-27.json).

The [exported repository graph](benchmarks/broken-dependency-repository-2026-10-27.svg) uses the same graph layout engine and captured import data. With the user's approval, the local development quota is now 10 through the ignored `.env` setting `MDT_LOCAL_MAX_PROJECTS_PER_USER=10`. The application and Compose fallback defaults remain five. No existing project was deleted or replaced.

The example is saved as **Historical broken dependencies - WebErpMesv2**. [Open its local graph](http://localhost:5173/#/projects?project=b4c648200dbd45599a17d2506f2707f3&job=a9b51d195b49480ebca21ba0eb41941b&view=graph) while signed in. The normal project-import API completed and retained the two flagged edges and both unresolved nodes. [Live import result](benchmarks/broken-dependency-live-2026-10-27.json).

The rebuilt local demo was verified in Browser: the target is visibly red, its incoming connection has the red broken-link stroke and badge, and the inspector explains that the dependency is an illustrative missing deployment target. [Browser screenshot](benchmarks/demo-broken-link-detail-2026-10-27.png).

The saved repository graph was also verified in Browser while signed in: selecting `worker` highlights the two red connections to `db` and `redis`. [Repository browser screenshot](benchmarks/repository-broken-links-browser-2026-10-27.png). Both graph tabs remain available for inspection.
