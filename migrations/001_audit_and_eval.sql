-- Phase 1 tables (architecture section 5). metadata_doc, join_edge and feedback
-- arrive with the phases that use them.

CREATE TABLE audit_log (
  request_id     UUID PRIMARY KEY,
  user_id        TEXT NOT NULL,
  role           TEXT NOT NULL,
  question       TEXT NOT NULL,
  final_sql      TEXT,
  exit_code      TEXT NOT NULL
    CHECK (exit_code IN ('answered', 'declined', 'clarified', 'failed_guard', 'error')),
  rows_returned  INT,
  bytes_scanned  BIGINT,
  model_calls    INT,
  model_cost_usd NUMERIC(10, 5),
  latency_ms     INT,
  trace_id       TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX audit_log_created_at_idx ON audit_log (created_at);

CREATE TABLE eval_run (
  run_id         UUID PRIMARY KEY,
  git_sha        TEXT,
  config         JSONB,
  golden_version TEXT,
  accuracy       NUMERIC(5, 4),
  by_slice       JSONB,
  cost_usd       NUMERIC(10, 4),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
