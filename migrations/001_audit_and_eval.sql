-- Phase 1 tables (architecture section 5). metadata_doc, join_edge and feedback
-- arrive with the phases that use them.

create table audit_log (
  request_id     uuid primary key,
  user_id        text not null,
  role           text not null,
  question       text not null,
  final_sql      text,
  exit_code      text not null
    check (exit_code in ('answered', 'declined', 'clarified', 'failed_guard', 'error')),
  rows_returned  int,
  bytes_scanned  bigint,
  model_calls    int,
  model_cost_usd numeric(10, 5),
  latency_ms     int,
  trace_id       text,
  created_at     timestamptz not null default now()
);
create index audit_log_created_at_idx on audit_log (created_at);

create table eval_run (
  run_id         uuid primary key,
  git_sha        text,
  config         jsonb,
  golden_version text,
  accuracy       numeric(5, 4),
  by_slice       jsonb,
  cost_usd       numeric(10, 4),
  created_at     timestamptz not null default now()
);
