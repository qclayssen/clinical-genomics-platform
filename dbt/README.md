# dbt — analytics-engineering transformation layer

A dbt project that rebuilds the platform's star-schema warehouse (staging
views over `runs`/`qc_metrics`/`qc_warnings`/`samples`, then `dim_*`/`fct_run`
marts) using the standard dbt toolchain: `ref()`/`source()` lineage, schema
tests, and generated docs.

## Why this exists alongside `db/schema.sql`'s hand-rolled warehouse

The `public.fact_run` materialized view and `public.dim_*` tables in
[`db/schema.sql`](../db/schema.sql) remain the warehouse Metabase actually
reads from in production — see [ADR-0023](../docs/adr/0023-star-schema-warehouse-airflow.md)
for why a plain `REFRESH MATERIALIZED VIEW` is the right call at this
project's scale and zero-cost constraint. This `dbt/` project is additive: it
demonstrates the same star schema built with dbt (models, `ref()` lineage,
`data_tests`, docs) in its own `analytics` Postgres schema, so it never
collides with the production tables. See [ADR-0025](../docs/adr/0025-dbt-analytics-engineering-layer.md)
for the full rationale.

## Layout

```
dbt/
├── dbt_project.yml
├── profiles.yml            # env-var-driven, no secrets — see below
└── models/
    ├── staging/             # 1:1 views over the OLTP source tables
    │   ├── stg_samples.sql
    │   ├── stg_runs.sql
    │   ├── stg_qc_metrics.sql
    │   ├── stg_qc_warnings.sql
    │   └── _staging.yml     # source declarations + schema tests
    └── marts/                # star-schema tables, one row per grain
        ├── dim_pipeline_version.sql
        ├── dim_caller.sql
        ├── dim_date.sql
        ├── fct_run.sql
        └── _marts.yml        # schema tests + relationships
```

## Running it

Needs a Postgres with `db/schema.sql` + `db/seed_demo.sql` already loaded —
the same database `docker-compose.yml` brings up.

```bash
pip install dbt-postgres

# docker-compose.yml's demo credentials (override via CGP_PG* env vars for
# a different target — see profiles.yml)
export DBT_PROFILES_DIR="$(pwd)/dbt"

cd dbt
dbt run    # builds staging views + marts tables into the `analytics` schema
dbt test   # unique/not_null/relationships/accepted_values checks
dbt docs generate && dbt docs serve   # browsable lineage graph + column docs
```

## What the tests catch

- `not_null`/`unique` on every natural and surrogate key.
- `relationships` tests enforcing every foreign key in the star schema
  (`fct_run.pipeline_version_key -> dim_pipeline_version`, etc.) — the same
  invariant `db/schema.sql`'s `JOIN`s rely on implicitly, made explicit and
  CI-checked here.
- `accepted_values` on `qc_warnings.overall_status`, matching the `CHECK`
  constraint in `db/schema.sql`.

Run in CI on every push/PR touching `dbt/**` — see
[`.github/workflows/dbt-ci.yml`](../.github/workflows/dbt-ci.yml).
