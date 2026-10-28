# Reproducible broken-dependency presentation example

Verified on 28 October 2026 against the current public source and the running MDT application.

## Recommended repository

- Repository: https://github.com/haduart/Thrift-Docker-HelloWorld-with-Java-Spring-and-Python-Server
- Default branch checked: `master`
- Exact revision checked and imported: `4972f72612a59ca8bbc18da0b7b15408149ec696`
- Compose source: https://github.com/haduart/Thrift-Docker-HelloWorld-with-Java-Spring-and-Python-Server/blob/4972f72612a59ca8bbc18da0b7b15408149ec696/docker-compose.yml
- Upstream report: https://github.com/haduart/Thrift-Docker-HelloWorld-with-Java-Spring-and-Python-Server/issues/1

`java-test-client` declares `depends_on: python`, while the declared server service is `python-thrift-server`. The selected Compose file does not declare `python`. The client's `PYTHON_THRIFT_SERVER` environment variable also names `python`.

## Verified MDT result

The complete source archive was read through the existing importer, first in an isolated registry with no live-store writes, then through the normal project-import UI. Repository source/build code was not executed.

- Nodes: `java-test-client`, `python-thrift-server`, and the unresolved `python` target.
- One captured dependency: `java-test-client → python`.
- Missing target flag: `is_broken: true`.
- Edge flag: `has_bug: true`.
- Connection issue: `UNDEFINED_COMPOSE_SERVICE`, severity `HIGH`.
- The live browser graph visibly shows the red target, red dashed edge, and broken-link badge. Its relation inspector names `docker-compose.yml` and explains the missing declaration.
- Archive SHA-256: `c87bac9b5c3c2e20a0467b2d68dfc2442deeece0c86e68dfb55962f2a0e559e0`.
- Canonical snapshot version: `2ab9f4d8e1fb65decb9a45f0ae1f3331e83e41fde9cc09020c4bb1a2df53173a`.

## Open for the presentation

Saved project: **Presentation — broken Thrift dependency**.

[Open the saved local graph](http://localhost:5173/#/projects?project=6828edc539d147d5b944a4e137a0f1f2&job=3ac2e39f176a4d9e95f7f67fe1210633&view=graph) while signed in. Choose **Expand graph**, then select the red connection to reveal its explanation.

Screenshots:

- [Graph](benchmarks/broken-thrift-graph-2026-10-28.png)
- [Connection explanation](benchmarks/broken-thrift-detail-2026-10-28.png)

Suggested presentation wording: “The Java client declares a startup dependency on `python`, but the deployment only defines `python-thrift-server`. MDT retains the missing target and marks the connection red, so the declaration mismatch is visible.”

This demonstrates an invalid captured configuration, not a measured runtime outage. Source coverage is partial, and the importer does not extract a complete Thrift communication model. The zero architectural-smell score is separate from the flagged connection issue and is not evidence that the application is safe.

## Larger alternative, independently verified

https://github.com/cskujawa/pterodactyl-single-server-docker-compose at `b9dd090baf9535c1d26c2a6453ca98b18ee0e0b4` also produces a genuine unresolved `nginx → app` dependency in MDT. Its root `docker-compose.yml` references `app` without declaring it; the repository declares `panel` instead. The isolated complete import produced seven nodes, three relations, and one `UNDEFINED_COMPOSE_SERVICE` issue. This alternative was not added to the live project store.

## Why WebErpMesv2 looked healthy

The WebErpMesv2 project in the user's screenshot was imported at `HEAD`, where its service names are corrected. Its earlier defect requires historical revision `7595d2abbffcf1f984a6aad1eca48e7630fbf3fc`; importing a repository URL without the historical revision does not reproduce it.
