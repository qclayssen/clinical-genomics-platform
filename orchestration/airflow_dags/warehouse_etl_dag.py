"""Illustrative Airflow DAG for the warehouse ETL.

Extracts run/QC/provenance records from DynamoDB into Postgres
(db/sync_dynamodb_to_postgres.py), then refreshes the star-schema
fact_run materialized view (db/schema.sql) that Metabase reads from.

Not deployed or run in CI — this repo's real compute is a locally-run
Nextflow pipeline with no scheduler attached (ADR-0017). This DAG documents
how the same two steps (sync, then warehouse refresh) would be scheduled
for near-real-time monitoring in a deployment that runs Airflow, per
ADR-0023. Needs environment: an Airflow instance with `apache-airflow` and
`apache-airflow-providers-postgres` installed, and a `cgp_postgres`
connection configured.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator

from db.sync_dynamodb_to_postgres import sync_all

default_args = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="cgp_warehouse_etl",
    description=(
        "Sync DynamoDB run metadata into Postgres, then refresh the "
        "fact_run warehouse view that Metabase dashboards read from."
    ),
    schedule="*/15 * * * *",  # near-real-time monitoring: every 15 minutes
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["warehouse", "etl", "metabase"],
) as dag:

    extract_load = PythonOperator(
        task_id="sync_dynamodb_to_postgres",
        python_callable=sync_all,
    )

    # dim_pipeline_version/dim_caller are identity-keyed tables (db/schema.sql),
    # not views — a new distinct value must be upserted before fact_run's
    # refresh joins against it, or that run is silently dropped.
    populate_dimensions = PostgresOperator(
        task_id="populate_dimensions",
        postgres_conn_id="cgp_postgres",
        sql="""
            INSERT INTO dim_pipeline_version (pipeline_version)
            SELECT DISTINCT pipeline_version FROM runs
            ON CONFLICT (pipeline_version) DO NOTHING;

            INSERT INTO dim_caller (caller)
            SELECT DISTINCT caller FROM runs
            ON CONFLICT (caller) DO NOTHING;
        """,
    )

    refresh_fact_run = PostgresOperator(
        task_id="refresh_fact_run",
        postgres_conn_id="cgp_postgres",
        sql="REFRESH MATERIALIZED VIEW CONCURRENTLY fact_run;",
    )

    extract_load >> populate_dimensions >> refresh_fact_run
