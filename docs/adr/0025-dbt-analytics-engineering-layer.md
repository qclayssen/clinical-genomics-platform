# ADR-0025: dbt as an additive analytics-engineering transformation layer

## Status

Accepted

## Context

[ADR-0023](0023-star-schema-warehouse-airflow.md) chose hand-rolled SQL
(`db/schema.sql`'s `dim_*` tables and `fact_run` materialized view, refreshed
by a scheduled job) as the warehouse Metabase reads from. That decision
still holds — see ADR-0023's rationale for why a plain
`REFRESH MATERIALIZED VIEW` is the right call at this project's scale and
zero-cost constraint, and it stays the production path.

dbt (staged sources, `ref()`-linked models, generic schema tests, generated
lineage docs) is the toolchain named in the target job description alongside
Airflow — a project demonstrating warehouse *design*, not just querying,
benefits from showing it, and dbt's test-and-document-your-transformations
discipline is a distinct, transferable skill from "wrote a materialized view
that works."

## Decision

Add a `dbt/` project that rebuilds the same star schema — `stg_*` staging
views over the OLTP tables, then `dim_pipeline_version`/`dim_caller`/
`dim_date`/`fct_run` marts — using dbt, in its own `analytics` Postgres
schema (via a custom `generate_schema_name` macro) so it never collides
with the `public.dim_*`/`public.fact_run` objects `db/schema.sql` defines.

It is additive and demonstrative, not a replacement:

- `db/schema.sql`'s objects remain what Metabase's dashboards and
  `dashboards/metabase/dashboard_manifest.yaml` actually query.
- `dbt/` is not part of `docker-compose.yml`'s auto-init — it's run
  separately (`cd dbt && dbt run && dbt test`), documented in
  [`dbt/README.md`](../../dbt/README.md).
- CI (`.github/workflows/dbt-ci.yml`) runs `dbt run`/`dbt test` against a
  seeded Postgres on every push/PR touching `dbt/**`, so the claim "this
  runs" is checked, not asserted — consistent with this repo's
  verified-vs-needs-environment honesty convention (root `CLAUDE.md`).

## Consequences

- Two warehouse implementations of the same shape now exist in the repo.
  That duplication is deliberate and documented (`dbt/README.md` explains
  why); it must not be allowed to silently drift into looking like the
  "real" pipeline reads from `dbt/`'s tables — it does not.
- dbt only ever reads from `samples`/`runs`/`qc_metrics`/`qc_warnings`. It
  has no write access to the insert-only tables and does not touch
  `run_provenance`/`audit_log`, so it cannot violate the insert-only /
  immutability invariant ([ADR-0005](0005-insert-only-postgres.md)).
- Schema tests (`not_null`, `unique`, `relationships`, `accepted_values`)
  encode the same foreign-key assumptions `db/schema.sql`'s `JOIN`s rely on
  implicitly — a useful cross-check if the OLTP schema ever changes shape.
