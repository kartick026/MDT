# Coverage indicators and scanner improvements — 24 October 2026

MDT now presents source scanning, syntax parser support, and runtime verification separately. Reading every eligible file does not establish complete architecture coverage or observed runtime communication.

## Implementation

- Repository imports record `coverage_schema_version: 2` and independent `coverage.indicators.source_scan`, `parser_support`, and `runtime_verification` measurements. Raw counts, omissions, excluded/unmapped source, missing service sources, and unsupported contracts remain available.
- The default source budget is now 500 files and 8 MiB, configurable through `REPO_SOURCE_MAX_FILES` and `REPO_SOURCE_MAX_TOTAL_BYTES`. The 256 KiB per-file limit remains. Entry points are prioritized in deterministic service round-robin order. Exhausted budgets and upstream rate limits stop additional requests. Unreadable source reserves a conservative budget allowance without inventing measured bytes.
- Valid TypeScript generic tagged templates have a narrowly checked compatibility path for the pinned Tree-sitter grammar's missing-`!` recovery. Original source, byte positions, route evidence, and compatibility diagnostics are preserved. Other syntax errors remain explicit failures; semantic comparison does not silently accept malformed code.
- Summary, Findings, Drift, Markdown/HTML reports, shared extension summaries, and VS Code results display the separate indicators. Responsive cards wrap their contents.
- Change analysis exposes `topology_coverage` separately from changed-file extraction in `coverage`. Historical jobs use their own saved snapshot. Re-importing a project does not change old counts or scores.
- Static evidence completeness no longer becomes partial solely because runtime was unmeasured. Real source, mapping, parser, and unresolved-contract gaps still qualify the assessment. The legacy overall `partial` flag remains for older clients; it is not a file-read percentage.

## Measured repository replay

All ten previously pinned public archives were replayed through the importer and detector. Archive hashes were verified; repository source was neither built nor executed. This was a cached replay, not ten new website imports or a predictive-accuracy benchmark. Commit-risk analysis was not rerun.

| Repository | Previous files read | Current eligible files read | Current syntax parsed | Other parser outcomes |
| --- | ---: | ---: | ---: | --- |
| DietrichGebert/ponytail | — | — | — | Architecture discovery abstained |
| GoogleCloudPlatform/microservices-demo | 57 | 57 / 57 | 17 | 40 heuristic |
| fastapi/full-stack-fastapi-template | 40 | 40 / 40 | 39 | 1 failed |
| dockersamples/example-voting-app | 8 | 8 / 8 | 6 | 1 heuristic, 1 bounded partial parse |
| microservices-demo/microservices-demo | 0 | 0 / 0 | 0 | No eligible mapped source; unavailable |
| spring-petclinic/spring-petclinic-microservices | 0 | 0 / 0 | 0 | No eligible mapped source; unavailable |
| open-telemetry/opentelemetry-demo | 100 | 161 / 161 | 115 | 45 heuristic, 1 failed |
| dotnet/eShop | 100 | 276 / 276 | 14 | 262 heuristic |
| saleor/saleor-platform | 0 | 0 / 0 | 0 | No eligible mapped source; unavailable |
| expressjs/express | — | — | — | Architecture discovery abstained |

Zero eligible files is unavailable coverage, never a complete scan. All imported runtime indicators remain unmeasured. Topology counts and architectural debt stayed unchanged across this replay; the broader reads improve evidence coverage without artificially changing scores.

The independent parser comparison covered all 111 captured frontend JS/TS files in OpenTelemetry at `ba1757b3f197916640fff4f7c549b99e54835ab8`: **106 parsed / 5 failed → 110 parsed / 1 failed**. Four valid generic-template files recovered: `Button.tsx`, `CartDropdown.styled.ts`, `ProductCard.styled.ts`, and `ProductDetail.styled.ts`. Imports, exports and route records were retained.

[Full replay evidence](benchmarks/coverage-replay-2026-10-24.json) · [Pinned parser evidence](benchmarks/parser-coverage-2026-10-24.json)

## Verification and bugs fixed

| Check | Result / defect covered |
| --- | --- |
| Full isolated backend suite | 389 passed, 12 external database integration tests skipped, 62.28 seconds |
| Final scanner tests after budget refinement | 39 passed, 4.60 seconds; includes one new unreadable-source regression, overlaps the full run |
| Frontend | 23 passed; lint and production build passed |
| Shared client / browser extension / VS Code | 8 / 10 / 10 passed; both extension builds passed |
| Canonical bundled demo | Recomputed comparison passed; no fabricated scan counts added |
| Historical API regression | Saved scan returned separately from change extraction; latest project import cannot replace historical counts; ownership checks retained |
| Scanner limits | More than 100 files, fair ordering, aggregate/per-file limits, missing and unreadable files, rate limiting, excluded/unmapped source, empty modules, unknown and contradictory counters |
| Parser limits | Generic tagged templates, comment-only equivalence, actual source changes, false route text, malformed syntax, optional-chain tags, nested unsupported recovery, byte/node limits |
| Local Docker | Backend readiness and Nginx configuration passed; frontend/backend refreshed without restarting the four-service fleet |
| Final restart and persistence | Docker Desktop was stopped at the final check and was restarted. All eight stack containers resumed; backend, Neo4j and Chroma were healthy, `/health/ready` returned `ready`, and the frontend returned HTTP 200. The global registry SHA-256 remained `62d9fa65357611e73aebbf67ecb10cc9c6aef98d4d4b997821abcf32b216658e`, matching the pre-import value. |
| Live website | Fresh pinned OpenTelemetry import `100228c6d47d4347b9693b5c5191ccf8` reported 161/161 read, 115/161 syntax parsed, 45 heuristic, 1 failed, runtime not measured |
| Historical website/export | Analysis `45fcef8b9e1e4e78a957db363b13ef26` retained 100/161 read and 53/100 syntax parsed after re-import; downloaded Markdown retained these separate measurements |
| Responsive layout | Summary and Findings at 320px; Drift at 320px and 1440px: inspected coverage cards had no horizontal overflow; normal viewport restored |

The first new historical API test used the project-creation response as if it contained a snapshot; its fixture was corrected to read the stored project and the full suite passed. Windows Python 3.14 async tests stalled during event-loop socket initialization before test bodies; Linux Docker supplied the successful full run. An initial automatic approval-review usage-limit failure prevented one Docker attempt; the later approved run succeeded.

## Remaining explicit limitations

- OpenTelemetry `_document.tsx` still encounters the pinned grammar's JSX attribute error at a literal `&display=swap`; it remains failed rather than suppressing arbitrary error nodes.
- The FastAPI template has one Python parse failure in `backend/app/api/deps.py` in the deployed Python runtime. Voting app's vendored `angular.min.js` reaches the syntax-node limit.
- Unmapped files, image-only services, unsupported language/framework contracts, and unresolved deployment helpers still limit static architecture interpretation. Raising the scan budget does not resolve these.
- Runtime tracing is not implemented by this change. No claim of complete runtime coverage, calibrated prediction accuracy, or deployment safety is made.
- The 12 PostgreSQL/Neo4j integration checks were not rerun against external databases in this isolated pass. Current extension source and build output are updated; the previously packaged ZIP/VSIX files have not been repackaged or published.

No commit, push, cloud deployment, or marketplace publication was performed.
