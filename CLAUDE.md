# Governed Analytics Agent

Text-to-SQL analytics agent over a snapshot of BigQuery
`thelook_ecommerce`, modelled with dbt. Design: docs/architecture.md.
Current state and approved decisions: docs/progress.md.
Read both at the start of every session. If you want to deviate from
either, stop and explain why first.

## Non-negotiable rules
- The model proposes, code decides. No LLM-generated SQL executes
  without the SQL guard.
  - Phase 1 guard: parse (sqlglot, BigQuery dialect), single SELECT,
    table/column allowlist from mart models, PII deny, edge exists in
    join graph, no cross joins, LIMIT, dry-run byte cap.
  - Phase 2 adds: fan-out, key-column and cardinality checks.
- The agent queries marts only, using the agent-readonly service account.
  No code path issues DDL or DML.
- Bounded workflow: max MAX_REPAIRS repair attempts (default 3), max 6
  model calls, 30 s deadline, 20 s warehouse timeout. No free agent
  loops, no multi-agent frameworks.
- dbt sources read from the snapshot dataset, never the public dataset.
- Golden tests (evals/golden/) are written by me. Never create, edit or
  "fix" golden questions, expected SQL or expected results. Never use
  them as retrieval examples (data/verified_queries/).
- PII columns (`meta: {pii: true}`) never reach marts, prompts, logs or
  sample values.
- No secrets in code, prompts, logs or commits. Env vars only; document
  every variable in .env.example.
- The ENV=dev user/role header stub must never work outside dev.
- Never report a metric or result you have not produced by running code.
  Quote the command and point to the output file.

## Environment
WSL2 Ubuntu, Docker Compose, uv, Python 3.12, dbt-bigquery.
Common commands: make up | migrate | test | test-integration | lint |
dbt-build. The `eval` and `api` targets are added in later steps.
Tests needing BigQuery are marked `bq`; tests needing local services
(Postgres) are marked `integration`. Both are opt-in via
`make test-integration`; `make test` deselects them and runs without
network access.

## How to work
- Start of session: read CLAUDE.md and docs/progress.md, run
  `git status` and `git log --oneline -10`, summarise where we are in
  3–4 lines, and wait before changing anything.
- Before a non-trivial change, write a short plan and wait for my OK.
- Stay inside the current step. Don't touch unrelated files. If you
  notice something outside scope, list it at the end instead.
- For risky code (guard, executor, auth, RLS, PII), write failing tests
  first, show them, then implement.
- Run `make lint` and `make test` before saying a task is done; show the
  output.
- Small commits, one logical change each. Show `git status` before
  committing.
- If something is unclear or a library behaves unexpectedly, ask.
- End of session: update docs/progress.md (done, decisions, exact next
  step) and commit.

## Coding style (Python)
- Python 3.12, full type hints, mypy strict must pass. No `Any` unless
  unavoidable, with a comment saying why.
- ruff for lint and format; line length 100.
- Small pure functions. Side effects (BigQuery, Postgres, model calls,
  clock) live behind thin interfaces in src/tools and are injected, so
  core logic is testable without network.
- Pydantic v2 models for every cross-boundary object; validate at the
  boundary, trust inside.
- Prefer Literal or Enum over free strings for fixed values.
- Errors: raise specific exceptions defined in src/core/errors.py; never
  bare `except`; never swallow errors. Expected failures on the request
  path (guard, executor, orchestrator, API) are return values with an
  exit code. CLI scripts may raise and map exceptions to process exit
  codes.
- Logging: structured logging via the standard logging module with a JSON
  formatter; include request_id; never log secrets, PII or result rows.
  No print() outside scripts/.
- Config only through src/core/config.py (pydantic-settings). No
  os.environ reads elsewhere. Tests get configuration through a
  Settings fixture, never os.environ.
- Prompts live in src/core/prompts/ as versioned files, never inline
  strings.
- Naming: snake_case functions and modules, PascalCase classes,
  UPPER_CASE constants. Descriptive names over abbreviations.
- Docstrings on public functions: one line on what it does, plus Args
  and Returns only when not obvious from types.
- Comments explain why, not what.
- Tests: pytest; one test file per module; names read as behaviour
  (`test_guard_rejects_delete_statement`); use fixtures and fakes, not
  real services, unless marked `bq`/`integration`.
- Dependencies: add only with a stated reason; pin in uv.lock.

## SQL and dbt style
- Lowercase keywords, one column per line in SELECT lists, trailing
  commas, explicit `as` for aliases.
- CTEs over nested subqueries; name CTEs by what they hold.
- Model layers: staging (`stg_`, 1:1 with source, rename and cast only),
  marts (`fct_`, `dim_`). Rename `id` to `<entity>_id` in staging.
- Every model has a description; every column has a description and
  type; primary keys have unique and not_null tests; foreign keys have
  relationships tests.
- Governed metrics are defined only in the semantic YAML, never
  duplicated in SQL elsewhere.

## Writing style (docs, README, ADRs, reports)
- Plain, direct English. Short sentences. Active voice.
- Lead with the conclusion, then the detail.
- Use tables for comparisons and results; prose for reasoning.
- Every number names its source (command, file, run id). Targets are
  labelled as targets; never present a target as a result.
- No marketing words (powerful, seamless, cutting-edge, robust).
- Use the same terms as docs/architecture.md (guard, mart, golden set,
  verified query, exit code).
- ADRs: Context, Decision, Alternatives, Consequences, Revisit if.
  One page max, in docs/adr/NNN-title.md.
- Eval reports: setup (git sha, model ids, golden version, reference
  date), results by slice, failures with examples, what changed since
  the last run.

## Commit and PR style
- Conventional Commits: feat:, fix:, test:, docs:, refactor:, chore:,
  with a scope, e.g. `feat(guard): reject cross joins`.
- Subject under 72 characters, imperative mood. Body explains why when
  it isn't obvious.
- Never commit .env, keys, dbt target/, or eval caches.