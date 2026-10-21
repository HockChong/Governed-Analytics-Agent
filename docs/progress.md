# Progress

Current state and approved decisions. Read with CLAUDE.md and
docs/architecture.md at the start of every session.

## Where we are

Phase 1 groundwork (architecture section 12). Settings, local Postgres,
migrations, the read-only warehouse identity and the thelook snapshot
exist. A style cleanup against CLAUDE.md is done. No dbt models, guard,
or API yet.

## Done

| Date | Change | Commit |
| --- | --- | --- |
| 2026-10-20 | ADR-007: local dbt Core v1 and MetricFlow, no dbt Cloud | aaeee7c |
| 2026-10-20 | Integration test: agent identity cannot create tables in BigQuery | 97c1589 |
| 2026-10-21 | CLAUDE.md, architecture doc, minimal README | f467260 |
| 2026-10-21 | Settings, local Postgres (compose), SQL migrations | a7e50fe |
| 2026-10-21 | CLAUDE.md rewritten with session workflow and style rules | d6ff4a8 |
| 2026-10-21 | Snapshot of thelook_ecommerce into `SNAPSHOT_DATASET`; dbt sources read it | b5d800e |
| 2026-10-21 | `bq` / `integration` markers opt-in; `make test` deselects them | 24c7a84 |
| 2026-10-21 | All config through `Settings`; integration tests use a `settings` fixture | a36dc20 |
| 2026-10-21 | `core/errors.py`; `bq.py` moved to `tools/`; CLIs moved to `scripts/` | 3f767b7 |
| 2026-10-21 | `snapshot()` takes injected clock and id generator | bedb9ad |
| 2026-10-21 | Pydantic `TableSnapshot` / `SnapshotMetadataRow`; `snapshot()` split into helpers | 711fff7 |
| 2026-10-21 | Docstrings, descriptive names, behaviour test names, lowercase SQL | ddccfda |

Verification on 2026-10-21 (after ddccfda):

| Command | Result |
| --- | --- |
| `make lint` | ruff clean; mypy strict "no issues found in 20 source files" |
| `make test` | 37 passed, 4 deselected |
| `make test-integration` | 4 passed, 37 deselected (live BigQuery and local Postgres) |
| `make test` with every socket connect blocked and gcloud config empty | 37 passed, 4 deselected (re-run at 9aadad8) |

## Decisions

- dbt Core v1.12 with local MetricFlow; no dbt Cloud (ADR-007).
- GCP dev resources were created by hand on 2026-10-20 to unblock week 1:
  project `governed-analytics-dev`, dataset `thelook_dbt` (US), service
  accounts `dbt-runner` and `agent-readonly`, used through impersonation
  with no key files. They are not in Terraform yet; import them in
  Phase 3 rather than recreate them.
- `bq` marks tests that need live BigQuery; `integration` marks tests that
  need local services (Postgres). `make test` runs
  `-m "not bq and not integration"` even when .env holds real credentials.
  `--strict-markers` is on so a typo cannot re-enable an opt-in test.
- Expected failures on the request path (guard, executor, orchestrator,
  API) are return values with an exit code. CLI scripts may raise and map
  exceptions to process exit codes (`scripts/snapshot.py`: 0 done,
  1 refused or unverified, 2 configuration missing).
- Tests get configuration through a `Settings` fixture, never os.environ.
  `tests/test_config.py` still sets env vars with monkeypatch, because it
  tests how `Settings` reads them.
- Code with side effects lives in `src/tools/` (`tools/bq.py`). CLI entry
  points and all `print()` live in `scripts/`.
- `snapshot()` requires `now` and `new_id`; `scripts/snapshot.py` passes
  the real clock and uuid4.
- Metadata timestamps are written as `isoformat()` ("+00:00"), the same
  form as before the Pydantic change.
- `pyyaml` is a direct dev dependency (tests import it).
- Descriptions in `dbt/models/sources.yml` are deferred to Part C.

## Not verified

- `make snapshot` has not been run against BigQuery since the refactor.
  Unit tests cover it with a fake client only.

## Next step

Step 1.1 in docs/build-plan.md (Part C start): profile the snapshot
tables, then descriptions, columns and PII tags in
`dbt/models/sources.yml`, then `stg_` models. Part C's full scope comes
from the user; record it here when it starts. docs/build-plan.md lists
the remaining steps for every phase, with model and prompt per step.

Before that, optionally run `make snapshot` once (it refuses to touch an
existing snapshot without `FORCE=1`) to confirm the refactored CLI still
works.

## Open items outside scope

- `AGENTS.md` (untracked) is a copy of the old CLAUDE.md and still says
  dbt reads the public dataset. Delete it or regenerate it from CLAUDE.md.
- README.md is stale: it says dbt reads
  `bigquery-public-data.thelook_ecommerce` and does not mention
  `make test-integration` or `make snapshot`.
- architecture.md section 11 summarises ADR-001 to ADR-006, but
  `docs/adr/` holds only ADR-007.
- `.claude/settings.json` (untracked) holds one-off permission entries
  from an earlier session.
- No structured JSON logging yet; CLAUDE.md requires it once request-path
  code exists.
- `core.autocrlf=true` produces LF/CRLF warnings on every commit. A
  `.gitattributes` with `* text=auto eol=lf` would make line endings
  explicit.
