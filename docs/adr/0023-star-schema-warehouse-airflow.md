# ADR-0023 — Star-schema warehouse layer + Airflow-orchestrated refresh

**Status:** Accepted (warehouse layer, implemented) / design note (Airflow DAG, illustrative) · **Date:** 2026-09-04

## Context

This project is periodically tailored toward specific job descriptions (see
[ADR-0022](0022-enterprise-data-platform-integration.md) for the precedent).
A Data Engineer role this platform is being tailored toward asks specifically
for "demonstrated data warehousing experience, including designing and
building a data warehouse rather than only querying one" and lists
orchestration/transformation tools such as Airflow as desirable, alongside
near-real-time monitoring and self-service analytics via a modern BI tool
(Metabase is explicitly named).

Before this ADR, `db/schema.sql` had a normalized OLTP shape (`runs`,
`qc_metrics`, `run_provenance`, `qc_warnings`) plus a handful of convenience
views (`v_run_summary`, `v_qc_warnings`, ...) that Metabase queried directly.
That's a reasonable small-scale design, but it doesn't demonstrate — or
benefit from — an actual dimensional model, and there was no orchestration
layer scheduling anything: the sync script and dashboard refresh were both
manual.

## Decision

**1. Add a star schema over the existing insert-only tables, not beside them.**
`dim_sample`, `dim_pipeline_version`, `dim_caller`, and `dim_date` are thin
views derived from `samples`/`runs` — no new source of truth, no risk of the
warehouse drifting from the OLTP tables. `fact_run` is a materialized view
(grain = one row per pipeline run) joining those dimensions with
`qc_metrics` and a rolled-up count of `qc_warnings`. It's materialized,
not a plain view, because Metabase dashboards should read a precomputed
table rather than re-run the join/aggregate on every card load — the
standard batch-warehouse pattern once a dashboard has more than a couple of
viewers.

**2. Document the refresh as a scheduled job, using Airflow.** Nextflow
(the pipeline orchestrator) and Step Functions (the AWS deployment
orchestrator, `infra/lib/`) already exist in this repo for different jobs;
neither is a natural fit for "periodically refresh a Postgres materialized
view." `orchestration/airflow_dags/warehouse_etl_dag.py` adds a two-task DAG
— sync DynamoDB → Postgres, then `REFRESH MATERIALIZED VIEW CONCURRENTLY
fact_run` — on a 15-minute schedule, which is what "near real-time
monitoring" means in a batch-warehouse context without standing up
streaming infrastructure that this scope doesn't need.

**3. Point new Metabase cards at the warehouse layer, not raw joins.**
`dashboards/metabase/README.md` gains cards for SLA/turnaround
percentiles, warehouse freshness, and a filterable self-service cohort
table — all reading `fact_run`/`dim_*` — demonstrating the
build-a-warehouse-then-report-off-it flow the role asks for, distinct from
the existing `v_run_summary`-based cards.

## Consequences

**Good**
- The star schema is additive and reversible: `fact_run` and the `dim_*`
  views can be dropped without touching any existing table, trigger, or
  view. Nothing that currently reads `v_run_summary` or the base tables
  needs to change.
- Demonstrates the specific distinction the role's selection criteria draws
  ("designing and building a data warehouse rather than only querying
  one") with a real, runnable artifact — `psql -f db/schema.sql` creates it
  today, no new dependency required.
- Keeps the demo/CI story unchanged (ADR-0017): the materialized view is
  created (and populated) by the same `schema.sql` load CI already runs;
  nothing about the Airflow DAG is required for the pipeline, tests, or
  Metabase dashboard to work.

**Bad / accepted limitations**
- The Airflow DAG is not deployed or exercised by CI — there's no Airflow
  instance in `docker-compose.yml`. It's a design artifact in the same
  spirit as `infra/` needing a real AWS account: structurally correct,
  not proof it's been run against a live scheduler.
- `fact_run` needs an explicit refresh (manual `REFRESH MATERIALIZED VIEW`,
  or the DAG) to pick up new rows — unlike `v_run_summary`, it is not
  always current. This is a deliberate batch/warehouse tradeoff, not an
  oversight, but it means the two layers answer slightly different
  questions ("what's true right now" vs. "what's true as of the last
  refresh") and both are kept rather than one replacing the other.
- A single 15-minute-cron DAG is not real orchestration complexity —
  no backfill logic, no sensors, no cross-DAG dependencies. That's
  intentional: this is a design note anchored to the platform's actual
  scale, not a simulation of enterprise Airflow usage.

## Alternatives considered

- **dbt instead of hand-written SQL views** — dbt is the more standard tool
  for exactly this transformation layer, and the views here are already
  expressed as versioned, testable SQL, so a dbt migration would be
  close to 1:1. Not adopted now because it adds a second toolchain
  (dbt Core + a profiles.yml + a separate `dbt run` step in CI) for a
  handful of views at this project's scale (ADR-0001) — noted here as the
  natural next step if the warehouse grows past a few fact/dim views.
- **A plain (non-materialized) `fact_run` view** — simpler, always current,
  no refresh scheduling needed. Rejected as the primary design because it
  doesn't demonstrate the batch-refresh pattern the orchestration piece of
  this ADR exists to show, and re-aggregating `qc_warnings` per dashboard
  load doesn't scale past demo size.
- **Cron instead of Airflow** — would satisfy "scheduled refresh" with far
  less code, but the role explicitly lists Airflow as desirable tooling, so
  the DAG form is deliberately chosen as the artifact worth having in the
  repo, at the cost of an ADR-flagged "not actually run anywhere" caveat.
