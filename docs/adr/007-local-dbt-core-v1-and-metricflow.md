# ADR-007 Local dbt Core v1 and MetricFlow, no dbt Cloud

**Status:** Accepted, 2026-10-20

**Context.** The architecture names "dbt semantic layer / MetricFlow" for the semantic layer
compiler without saying whether it is hosted. dbt Cloud's Semantic Layer APIs need an account
and a paid plan. Separately, dbt v2 became the default for new installs; its default build is
under the dbt v2 license (an Apache 2.0 open-source v2 also exists), it installs outside the
Python dependency tree, and compatibility with the `dbt-metricflow` package was not confirmed.

**Decision.** Use dbt Core 1.12 with `dbt-bigquery` and `dbt-metricflow`, pinned in `uv.lock`.
The semantic layer compiler calls MetricFlow locally to produce SQL, which then passes through
the SQL guard like any other candidate. dbt connects with OAuth and impersonates the
`dbt-runner` service account; no key files.

**Alternatives.** dbt Cloud Semantic Layer API; dbt v2 (default or open-source build).

**Consequences.** Zero cost and no sign-up for anyone running the project; one lockfile for
all Python tooling. We stay on the v1 line and will need a migration later.

**Revisit if.** MetricFlow is confirmed to work with open-source dbt v2, or dbt Core v1
support end is announced.
