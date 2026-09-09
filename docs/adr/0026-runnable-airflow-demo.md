# ADR-0026: Make the Airflow warehouse-ETL DAG runnable, not just illustrative

## Status

Accepted

## Context

[ADR-0023](0023-star-schema-warehouse-airflow.md) added
`orchestration/airflow_dags/warehouse_etl_dag.py` as a design artifact —
correct DAG structure, but never executed, because its first task
(`sync_dynamodb_to_postgres`) needs a real DynamoDB table, and this repo
deliberately has no AWS account (ADR-0012, zero-cost constraint). A DAG that
has never actually run is a weaker portfolio artifact than one that has.

## Decision

Give `db/sync_dynamodb_to_postgres.py` a **demo mode**: when
`CGP_METADATA_SOURCE=fixture`, `sync_all()` reads DynamoDB-shaped items from
a committed JSON fixture ([`tests/fixtures/dynamodb_items_demo.json`](../../tests/fixtures/dynamodb_items_demo.json))
instead of scanning a real table — same function, same downstream code path,
different input source. The `CGP_METADATA_SOURCE`/`CGP_METADATA_FIXTURE` env
vars default to the real DynamoDB path, so nothing about the production
behavior changes.

Add `docker-compose.airflow.yml`, an overlay (not part of the default
`docker-compose.yml` stack) that boots `apache/airflow:2.9.3` in standalone
mode with `CGP_METADATA_SOURCE=fixture` set, pointed at the same Postgres the
main compose file brings up. `docker compose -f docker-compose.yml -f
docker-compose.airflow.yml up -d` then lets a reviewer actually trigger
`cgp_warehouse_etl` and watch all three tasks succeed.

Add CI coverage for the piece that *can* run without a full Airflow instance:
a `sync-fixture-demo` job in `.github/workflows/db-ci.yml` runs
`sync_dynamodb_to_postgres.py` in fixture mode against a Postgres service
container and asserts the two demo runs land in `runs`. This is checked on
every push/PR, unlike the full Airflow boot (too slow/heavy for CI, run and
documented as verified manually — see `orchestration/README.md`).

### Why a fixture file, not a mocked DynamoDB endpoint (moto/LocalStack)

A JSON fixture is simpler, has zero new dependencies, and — because
`sync_all()` already accepted a pre-fetched `items` list (for its Lambda
call path) — required no change to the sync/insert logic at all, only to how
items are *sourced*. A mocked DynamoDB endpoint would exercise `boto3`'s
wire protocol, which isn't the part of this system that's actually in
question; the insert/idempotency logic is already covered directly by
`sync_run()`'s implementation reading `items` regardless of origin.

## Consequences

- The DAG is now demonstrably runnable, not just structurally plausible —
  verifiable in under two minutes with no AWS account.
- `docker-compose.airflow.yml` is deliberately not part of the default
  `docker compose up`: Airflow standalone takes real memory/CPU and ~60-90s
  to initialize, which would slow down the lightweight Metabase/demo-app
  walkthrough most reviewers want first.
- Demo mode adds a small permanent branch (`CGP_METADATA_SOURCE`) to
  production code. Kept minimal on purpose: one function
  (`load_source_items`) decides source, everything downstream is unchanged.
