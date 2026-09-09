# Orchestration — warehouse ETL scheduling

This directory holds the Airflow DAG scheduling the platform's extract/load
and warehouse-refresh steps (a desirable skill for this project's target
roles, alongside the AWS Step Functions orchestration already implemented in
`infra/lib/`). See [ADR-0023](../docs/adr/0023-star-schema-warehouse-airflow.md)
and [ADR-0026](../docs/adr/0026-runnable-airflow-demo.md).

## Run it

```bash
docker compose -f ../docker-compose.yml -f ../docker-compose.airflow.yml up -d
# Airflow UI at http://localhost:8080 — admin password is in
# `docker compose logs airflow` on first boot.
```

Then, in the Airflow UI (or `airflow dags trigger cgp_warehouse_etl` inside
the container), unpause and trigger `cgp_warehouse_etl`. It runs against
`docker-compose.yml`'s Postgres, syncing the demo fixture
([`tests/fixtures/dynamodb_items_demo.json`](../tests/fixtures/dynamodb_items_demo.json))
in place of a real DynamoDB table — no AWS account needed. See
[ADR-0026](../docs/adr/0026-runnable-airflow-demo.md) for why a fixture and
not a mocked DynamoDB endpoint.

## What it does

`airflow_dags/warehouse_etl_dag.py` runs three tasks (scheduled every 15
minutes in a real deployment; triggered on demand here):

1. **`sync_dynamodb_to_postgres`** — the existing
   [`db/sync_dynamodb_to_postgres.py`](../db/sync_dynamodb_to_postgres.py)
   script, wrapped in a `PythonOperator`. Reads from DynamoDB by default;
   `CGP_METADATA_SOURCE=fixture` (set in `docker-compose.airflow.yml`) makes
   it read `tests/fixtures/dynamodb_items_demo.json` instead — same function,
   same code path, different input.
2. **`populate_dimensions`** — idempotently upserts any pipeline_version/
   caller not yet in `dim_pipeline_version`/`dim_caller` (identity-keyed
   tables, not views — see [`db/schema.sql`](../db/schema.sql)). Must run
   before the refresh, or a run with a brand-new pipeline_version/caller
   has nothing to join to and is silently dropped from `fact_run`.
3. **`refresh_fact_run`** — `REFRESH MATERIALIZED VIEW CONCURRENTLY fact_run;`
   against the star-schema view defined in
   [`db/schema.sql`](../db/schema.sql), so Metabase dashboards see fresh data
   without recomputing joins/aggregates on every card load.

## What's still a design artifact vs. what's verified

- **Verified running:** the DAG itself, end-to-end, against a real Airflow
  instance and Postgres (see the "Run it" section above; also covered by
  CI's `sync-fixture-demo` job in `.github/workflows/db-ci.yml`, which runs
  `db/sync_dynamodb_to_postgres.py` in fixture mode without Airflow).
- **Still a design artifact:** the DynamoDB source itself (this repo has no
  AWS account — see [ADR-0012](../docs/adr/0012-dynamodb-primary-store.md))
  and running Airflow as a persistent, scheduled service rather than an
  on-demand local demo.

## Why a materialized view + scheduled refresh instead of a live view

`fact_run` joins `runs`, `qc_metrics`, and a correlated-subquery count over
`qc_warnings` — cheap at demo scale, but exactly the kind of join Metabase
dashboards should not repeat on every card render at production scale. A
materialized view refreshed on a schedule is the standard batch-warehouse
pattern for that; `CONCURRENTLY` keeps the view queryable during the
refresh instead of locking readers out.
