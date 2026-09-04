# Orchestration — warehouse ETL scheduling

This directory holds an illustrative Airflow DAG showing how the platform's
extract/load and warehouse-refresh steps would be scheduled in a deployment
that runs Airflow (a desirable skill for this project's target roles,
alongside the AWS Step Functions orchestration already implemented in
`infra/lib/`). See [ADR-0023](../docs/adr/0023-star-schema-warehouse-airflow.md).

## What it does

`airflow_dags/warehouse_etl_dag.py` runs three tasks every 15 minutes:

1. **`sync_dynamodb_to_postgres`** — the existing
   [`db/sync_dynamodb_to_postgres.py`](../db/sync_dynamodb_to_postgres.py)
   script, unchanged, wrapped in a `PythonOperator`.
2. **`populate_dimensions`** — idempotently upserts any pipeline_version/
   caller not yet in `dim_pipeline_version`/`dim_caller` (identity-keyed
   tables, not views — see [`db/schema.sql`](../db/schema.sql)). Must run
   before the refresh, or a run with a brand-new pipeline_version/caller
   has nothing to join to and is silently dropped from `fact_run`.
3. **`refresh_fact_run`** — `REFRESH MATERIALIZED VIEW CONCURRENTLY fact_run;`
   against the star-schema view defined in
   [`db/schema.sql`](../db/schema.sql), so Metabase dashboards see fresh data
   without recomputing joins/aggregates on every card load.

## Needs environment

This DAG is not run in CI and there is no Airflow instance in this repo's
Docker Compose file — it is a design artifact, matching how `infra/` needs
an AWS account to actually deploy. To run it for real: install
`apache-airflow` and `apache-airflow-providers-postgres`, place the file
under Airflow's `dags/` folder, and configure a `cgp_postgres` connection
pointing at the same database `docker-compose.yml` brings up.

## Why a materialized view + scheduled refresh instead of a live view

`fact_run` joins `runs`, `qc_metrics`, and a correlated-subquery count over
`qc_warnings` — cheap at demo scale, but exactly the kind of join Metabase
dashboards should not repeat on every card render at production scale. A
materialized view refreshed on a schedule is the standard batch-warehouse
pattern for that; `CONCURRENTLY` keeps the view queryable during the
refresh instead of locking readers out.
