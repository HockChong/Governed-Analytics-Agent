# Build plan

Step-by-step plan for the five phases in architecture section 12, with
the Claude Code model and a starting prompt for each step, and the models
the agent calls at runtime. Progress against it lives in docs/progress.md.
If a step here conflicts with architecture.md or progress.md, those win;
raise the conflict before changing anything.

## How to run a step

Open every session with:

> Start of session per CLAUDE.md. Then: **‹step prompt›**. Write a short
> plan and wait for my OK.

CLAUDE.md already covers the rest: failing tests first for risky code,
`make lint` and `make test` with output, small commits, progress.md at
the end. A step may take more than one session.

Claude Code model choice (switch with `/model`):

| Model | Use for |
| --- | --- |
| Opus 5.5 | Default. Anything touching correctness or safety: guard, PII, joins, auth, executor, metrics. |
| Sonnet 5.5 | Mechanical work: docs, YAML descriptions, CI and Terraform boilerplate, UI, running and reporting evals. |
| Fable 5.1 | A few high-stakes design or review sessions only (2.5× Opus per-token price). Good fit: `/code-review` on guard and RLS code before an exit gate. |

## Phase 1: MVP (weeks 1–3)

Exit gate: end-to-end answer on all 50 golden questions; baseline
accuracy recorded.

User task, start now: write the 50 golden questions in `evals/golden/`
(slowest item in the risk table; Claude must not write them).

| Step | Model | Prompt |
| --- | --- | --- |
| 1.1 Sources and staging (Part C start) | Opus 5.5 | Step 1.1: profile the 7 snapshot tables (columns, types, row counts, date ranges) with a script in scripts/. Add descriptions, columns and `meta: {pii: true}` to sources.yml per architecture §1. Build `stg_` models (rename and cast only, `id` → `<entity>_id`). PII must not pass beyond staging. |
| 1.2 Marts | Opus 5.5 | Step 1.2: build fct_order_items, fct_orders, dim_customers, dim_products, fct_sessions per architecture §1, with unique/not_null on keys and relationships tests on foreign keys. Add a test that no mart column is PII. Show `make dbt-build`. |
| 1.3 Metrics | Opus 5.5 | Step 1.3: define the 6–10 governed metrics from architecture §1 in semantic YAML only. Check each with `mf query` and record the command and output. |
| 1.4 Phase 1 guard (risky) | Opus 5.5 | Step 1.4: Phase 1 SQL guard in src/tools/guard.py. Failing tests first from a malicious-SQL corpus: DDL/DML, multiple statements, non-mart tables, PII columns, joins not in the graph, cross joins, no LIMIT, byte cap via a faked dry run. Show them, wait, then implement. Allowlist from manifest marts. Rejections return a ValidationResult, not exceptions. |
| 1.5 Executor and model client | Opus 5.5 | Step 1.5: executor in src/tools/executor.py (agent-readonly, 20 s timeout, maximum_bytes_billed, request_id job label, row cap) and a thin Anthropic client in src/tools/llm.py. Add the `anthropic` dependency with a stated reason. Fakes for both; executor tests first. |
| 1.6 Naive retrieval | Opus 5.5 | Step 1.6: render table, column and metric cards from the manifest (no PII sample values) and retrieve with Postgres full-text search. Add a migration for metadata_doc. |
| 1.7 Orchestrator and `/ask` | Opus 5.5 | Step 1.7: Phase 1 orchestrator as a plain state machine: retrieve → generate SQL → guard → execute → answer, enforcing MAX_REPAIRS, 6 model calls and 30 s. Versioned prompts in src/core/prompts/. FastAPI `POST /ask` with the dev-only header stub, one audit_log row per request, JSON logging with request_id. |
| 1.8 Eval harness | Opus 5.5 | Step 1.8: eval runner over evals/golden/ (don't create or edit any golden item). Implement the result comparison rules in architecture §9, cache model calls by input hash, write eval_run rows, add a `make eval` target. Test the comparator with hand-made result pairs. |
| 1.9 Baseline | Sonnet 5.5 | Step 1.9: run `make eval` on the 50 questions and write docs/eval-report.md in the CLAUDE.md eval-report format. Only numbers from the run, with command and run id. |

## Phase 2: Advanced AI (weeks 4–6)

Exit gate: ablation table showing each addition's effect.

| Step | Model | Prompt |
| --- | --- | --- |
| 2.1 Metadata pipeline and hybrid index | Opus 5.5 | Step 2.1: incremental indexing by content hash, embed only changed cards, pgvector + FTS. Architecture says Dagster: propose Dagster now or a script first, and explain before deviating. |
| 2.2 Retrieval fusion and reranker | Opus 5.5 | Step 2.2: reciprocal rank fusion of BM25 and vector results, rerank top 50 to top 15. Measure table recall@15 before and after. |
| 2.3 Join graph | Opus 5.5 | Step 2.3: build join_edge from dbt relationships tests, key tests and semantic entities (architecture §6), plus a nightly cardinality check that disables violated edges. |
| 2.4 Phase 2 guard (risky) | Fable 5.1 for design and tests, Opus 5.5 to implement | Step 2.4: fan-out, key-column and cardinality rules exactly as in architecture §6. Tests first, including tagged fan-out cases; show and wait. |
| 2.5 Structured plan and semantic routing | Opus 5.5 | Step 2.5: QueryPlan via structured outputs. Validate the plan's join path before SQL generation. Route governed metrics through MetricFlow compile. |
| 2.6 Repair, checks, clarify and decline | Opus 5.5 | Step 2.6: repair loop using guard errors, result checker (grain, reconciliation, plausibility), clarify and decline, exit codes 1–5 per architecture §4. |
| 2.7 Verified queries | Opus 5.5 | Step 2.7: data/verified_queries/ loader with provenance, and a CI check that fails if any golden question has cosine similarity > 0.95 to a verified query. |
| 2.8 Ablation | Sonnet 5.5 | Step 2.8: run the ablation (no semantic layer, no reranker, no verified queries, no repair) and add the results table to the eval report. |

## Phase 3: Production engineering (weeks 7–9)

Exit gate: RLS and injection suites 100% in CI; two-role demo works.

| Step | Model | Prompt |
| --- | --- | --- |
| 3.1 OIDC and role mapping (risky) | Opus 5.5 | Step 3.1: verify the OIDC token (signature, expiry, audience), map groups to warehouse roles, keep the header stub dev-only. Tests first. |
| 3.2 Terraform and RLS | Opus 5.5 | Step 3.2: Terraform. Import the hand-made GCP resources (see progress.md), add per-role SAs (sales_apac, finance_global), row access policies on thelook_dbt, PII policy tags. Show plan output; no apply without my OK. |
| 3.3 Security suites | Fable 5.1 | Step 3.3: RLS leakage suite and prompt-injection suite (poisoned product names, extraction prompts) per the architecture §7 threat model. Review gaps against OWASP LLM01–10. |
| 3.4 Reliability | Opus 5.5 | Step 3.4: retries with jitter, circuit breaker, per-user rate limit, request_id idempotency per architecture §10. Inject the clock. |
| 3.5 Docker and CI | Sonnet 5.5 | Step 3.5: Dockerfile and GitHub Actions: lint, type check, unit tests, security suites, smoke eval. Integration tests stay opt-in. |

## Phase 4: Eval and optimisation (weeks 10–11)

Exit gate: eval report with confidence intervals and cost–quality
comparison.

User task: grow the golden set to 150–300 questions with tags.

| Step | Model | Prompt |
| --- | --- | --- |
| 4.1 CI eval gate | Opus 5.5 | Step 4.1: CI eval gate with the architecture §9 thresholds, a 40-question smoke set per commit, and a tag validator for golden items. |
| 4.2 Caching | Opus 5.5 | Step 4.2: prompt caching for the static prefix (verify with cache_read_input_tokens) and a semantic cache keyed on question + role + index SHA. |
| 4.3 Routing experiments | Opus 5.5 | Step 4.3: run each model step on Haiku 5.5, Sonnet 5.5 and Opus 5.5 at low effort. Report accuracy by slice, cost and p95. Apply the ADR-004 revisit rule. |
| 4.4 Benchmark and taxonomy | Sonnet 5.5 | Step 4.4: 100-question BIRD or Spider 2.0-lite subset with fixed seeds; error taxonomy from failures; final eval report with 95% CIs. |

## Phase 5: Deploy and portfolio (weeks 12–14)

Exit gate: a stranger can run it from the README; results table matches
the eval report.

| Step | Model | Prompt |
| --- | --- | --- |
| 5.1 Cloud Run | Opus 5.5 | Step 5.1: staging and prod on Cloud Run via Terraform, smoke eval on staging, manual promotion. |
| 5.2 Review UI and feedback | Sonnet 5.5 | Step 5.2: review UI and feedback loop per architecture §8; a fix lands as a PR plus a paraphrased held-out test. |
| 5.3 Dashboards | Sonnet 5.5 | Step 5.3: OpenTelemetry traces to Langfuse or Phoenix; cost and SLO alerts per architecture §10. |
| 5.4 Docs | Sonnet 5.5 | Step 5.4: README results table from the eval report, ADR-001 to ADR-006 as files, threat model, runbook. |

## Runtime models

Keep the current `Settings` defaults, which match ADR-004:
`PRIMARY_MODEL=claude-sonnet-5-5`, `SMALL_MODEL=claude-haiku-5-5`.

| Role | Model | Effort | Reason |
| --- | --- | --- | --- |
| Classify intent | Haiku 5.5 | low | Simple, high-volume |
| Clarifying question | Haiku 5.5 | low | Short output |
| Plan (QueryPlan) | Sonnet 5.5 | medium | Join and grain judgment |
| SQL generation and repair | Sonnet 5.5 | medium | Same |
| Answer writer | Haiku 5.5 | low | Code verifies every number |
| LLM judge (answer text only) | Sonnet 5.5 | medium | Calibrate on 60 hand labels (architecture §9) |
| Embeddings | Not Claude | — | No first-party Anthropic embeddings endpoint assumed (verify). `VECTOR(1024)` fits Voyage or a local bge-m3. |
| Phase 4 comparison arm | Opus 5.5 | low | Test the stronger model at low effort before keeping two tiers |

List prices per 1M tokens (Claude API reference, cached 2026-10-06):

| Model | Input | Output | Cache read |
| --- | --- | --- | --- |
| Haiku 5.5 (prompts ≤ 100K) | $0.10 | $0.50 | — |
| Sonnet 5.5 | $2.00 | $10.00 | $0.20 |
| Opus 5.5 | $4.00 | $20.00 | $0.20 |

Cost check (estimate, not a measurement). Target: mean model cost ≤ $0.02
per question. Assuming a 5K cached prefix, 2K fresh input and about 600
output tokens including thinking, one Sonnet call costs about $0.011.
Plan plus SQL is two calls (about $0.022); the Haiku calls add about
$0.001. That is roughly $0.023 before any repair, so the target is tight.
Levers: merge plan and SQL into one call, shrink retrieved context, lower
effort. Measure in step 1.9.

API constraints that shape steps 1.5, 1.7 and 2.5 (Claude API reference):

- Forced `tool_choice` (`any` or a named tool) returns a 400 on Sonnet
  5.5. Get QueryPlan JSON through structured outputs instead.
- Non-default sampling values (e.g. temperature 0) return a 400 on Sonnet
  5.5 and Haiku 5.5, so eval runs cannot be made repeatable that way.
  Cache model calls by input hash instead.
- Thinking cannot be disabled on Sonnet 5.5; lower effort to limit it.
  Thinking tokens bill as output, so count them in `model_cost_usd`.
- Check `stop_reason == "refusal"` and map it to an exit code. A
  server-side refusal fallback exists on the Claude API only.
