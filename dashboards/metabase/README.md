# Metabase dashboard — "Clinical Genomics Ops"

The operational view a lab director would open each morning. Metabase questions are
defined as SQL here so the dashboard is version-controlled and reproducible rather
than clicked together and lost.

## Setup

```bash
# 1. Bring up Postgres + Metabase
docker compose -f docker-compose.yml up -d      # (compose file at repo root)
# 2. Load schema + demo data so cards render immediately
psql "$CGP_DB_URL" -f db/schema.sql
psql "$CGP_DB_URL" -f db/seed_demo.sql
# 3. The warehouse layer (fact_run + dims, cards 7-10 below) was created
#    empty by schema.sql before the seed data existed — populate the
#    dimensions, then refresh fact_run:
psql "$CGP_DB_URL" -c "
  INSERT INTO dim_pipeline_version (pipeline_version)
  SELECT DISTINCT pipeline_version FROM runs ON CONFLICT (pipeline_version) DO NOTHING;
  INSERT INTO dim_caller (caller)
  SELECT DISTINCT caller FROM runs ON CONFLICT (caller) DO NOTHING;
"
psql "$CGP_DB_URL" -c "REFRESH MATERIALIZED VIEW fact_run;"
# 4. In Metabase, add the Postgres DB, then create one Native Question per query below.
```

Cards 1–6 read the `v_run_summary` view; cards 7–10 read the warehouse
layer (`fact_run` + `dim_*`) — see `db/schema.sql`.

## Cards

### 1. Validation pass rate (single stat)
```sql
SELECT round(100.0 * avg(validation_pass::int), 1) AS pass_rate_pct
FROM v_run_summary;
```

### 2. SNV F1 trend across pipeline versions (line)
```sql
SELECT pipeline_version, caller, round(avg(snp_f1)::numeric, 4) AS mean_f1,
       count(*) AS n_runs
FROM v_run_summary
GROUP BY pipeline_version, caller
ORDER BY pipeline_version, caller;
```

### 3. Turnaround time per run (bar)
```sql
SELECT run_id, sample_id, round(turnaround_min::numeric, 1) AS turnaround_min
FROM v_run_summary
ORDER BY started_at DESC
LIMIT 20;
```

### 4. Cohort QC: duplication rate distribution (bar / histogram)
```sql
SELECT sample_id, round((percent_duplication*100)::numeric, 1) AS dup_pct
FROM v_run_summary
ORDER BY dup_pct DESC;
```

### 5. Failures needing review (table, conditional-highlighted)
```sql
SELECT run_id, sample_id, pipeline_version, caller,
       round(snp_f1::numeric, 4) AS snp_f1, started_at
FROM v_run_summary
WHERE validation_pass = false
ORDER BY started_at DESC;
```

### 6. Runs per week (line — throughput)
```sql
SELECT date_trunc('week', started_at) AS week, count(*) AS runs
FROM v_run_summary
GROUP BY 1 ORDER BY 1;
```

## Warehouse-layer cards

Cards 1–6 read the OLTP convenience view `v_run_summary`. The cards below
read the star schema instead (`fact_run` + `dim_*`, added in
[ADR-0023](../../docs/adr/0023-star-schema-warehouse-airflow.md)) — the
distinction a "build a warehouse, not just query one" role cares about:
precomputed, dimensionally modelled, and refreshed on a schedule (see
[`orchestration/`](../../orchestration/)) rather than joined fresh per card.

### 7. Turnaround SLA — p50 / p95 by pipeline version (bar)
Percentile queries over a rolling window are the kind of "deep-dive SQL
analysis" question an ops stakeholder actually asks ("are we meeting our
turnaround SLA, not just what's the average").
```sql
SELECT pipeline_version,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY turnaround_min) AS p50_min,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY turnaround_min) AS p95_min,
       count(*) AS n_runs
FROM fact_run
GROUP BY pipeline_version
ORDER BY pipeline_version;
```

### 8. Warehouse freshness (single stat, near-real-time monitoring)
Surfaces staleness of the materialized view itself — the question anyone
building on a batch-refreshed warehouse needs answered before trusting a
dashboard. Pair with a Metabase alert (see below) rather than only a card.
```sql
SELECT round(EXTRACT(EPOCH FROM (now() - max(started_at))) / 60.0, 1)
       AS minutes_since_last_run
FROM fact_run;
```

### 9. Self-service cohort explorer (table, with dashboard filters)
A single filterable table is the "self-service analytics" ask: add Metabase
dashboard filters bound to `{{sample_id}}`, `{{caller}}`, and
`{{pipeline_version}}` so a non-technical stakeholder can slice the cohort
themselves without writing SQL, instead of asking for a one-off query each
time. Click-built through the UI, these can be true Field Filters (bound to
a live Metabase column, with the search-as-you-type widget); created via
`provision_metabase.py` they come through as plain SQL Variables instead —
a real Field Filter needs the target column's Metabase field ID, which only
exists after Metabase finishes syncing the database schema, a round trip
the script doesn't perform. See `template_tags_for()` in
`provision_metabase.py` and [ADR-0024](../../docs/adr/0024-metabase-as-code-and-oss-sandboxing.md).
```sql
SELECT run_id, sample_id, pipeline_version, caller, started_at,
       round(turnaround_min::numeric, 1) AS turnaround_min,
       round(snp_f1::numeric, 4) AS snp_f1, n_warn, n_fail
FROM fact_run
WHERE 1=1
  [[AND sample_id = {{sample_id}}]]
  [[AND caller = {{caller}}]]
  [[AND pipeline_version = {{pipeline_version}}]]
ORDER BY started_at DESC;
```

### 10. QC warning rate trend, warehouse-backed (line)
Same intent as card 4, but reading the precomputed per-run warning counts
in `fact_run` instead of re-aggregating `qc_warnings` — the version that
scales once the dashboard has real viewers.
```sql
SELECT date_key, sum(n_warn) AS warn_count, sum(n_fail) AS fail_count
FROM fact_run
GROUP BY date_key
ORDER BY date_key;
```

## Other Metabase capabilities worth wiring up

Beyond adding cards, these are the "modern BI tool" features that turn a
handful of SQL questions into the kind of operational/self-service surface
the role description asks for:

- **Alerts** on card 8 (warehouse freshness) and card 5 (failures needing
  review) — Metabase can email/Slack when a single-stat card crosses a
  threshold, turning the dashboard from something a lab director checks
  into something that pages them.
- **Dashboard filters / Field Filters** wired to `dim_pipeline_version`,
  `dim_caller`, and `dim_sample` — card 9 above uses SQL-level `{{}}`
  variables; the same fields also work as native GUI filters on
  Metabase-built (non-SQL) questions once analysts start building their own.
- **X-rays / auto-explore** on `fact_run` for ad-hoc exploration during a
  stakeholder conversation, without pre-writing a card.
- **Collections + permissions** separating an "Ops" collection (cards 1, 3,
  5, 6, 8) from an "Analytics" collection (cards 2, 4, 7, 9, 10) mirrors how
  a real org scopes self-service access by audience — see `dashboard_manifest.yaml`
  below, which encodes this exact split.

## Provisioning as code

Rather than clicking each card together by hand, `dashboard_manifest.yaml`
declares the database connection, both collections, and all ten cards as
data, and `provision_metabase.py` creates them via the Metabase REST API —
idempotently, so re-running it against an existing instance is safe. It
also enables signed embedding on the Ops dashboard. See
[ADR-0024](../../docs/adr/0024-metabase-as-code-and-oss-sandboxing.md) for
why this replaces the old "run the serialization export" step, and
`tests/test_provision_metabase.py` for coverage (mocked API, no live
Metabase needed to verify the request payloads are correct).

```bash
pip install -r dashboards/metabase/requirements.txt
MB_USERNAME=admin@example.com MB_PASSWORD=... python dashboards/metabase/provision_metabase.py
```

Needs environment: a running Metabase instance with an admin account
already created (first-run setup wizard) — not run in CI.

## Row sandboxing without Metabase Enterprise

Metabase's native Data Sandboxing (row filtering by user attribute) is a
Pro/Enterprise feature. `db/sandboxing_demo.sql` demonstrates the
open-source-achievable equivalent: a Postgres view (`v_fact_run_secured`)
that filters `fact_run` by `current_user` against a `dim_sample_access`
mapping table, with two demo roles each granted `SELECT` on the view only —
never on `fact_run` or the mapping table directly. In Metabase, this maps
to one database connection per role, each assigned to its own permission
group, instead of Enterprise's single-connection-plus-attribute model. See
[ADR-0024](../../docs/adr/0024-metabase-as-code-and-oss-sandboxing.md) for
the full writeup, including the honest limits of this approximation.

```bash
psql "$CGP_DB_URL" -f db/sandboxing_demo.sql
psql "$CGP_DB_URL" -U cgp_analyst_cohort_a -c "SELECT sample_id FROM v_fact_run_secured;"
```

## Exporting for version control

`dashboard_manifest.yaml` (above) is the version-controlled artifact for
this dashboard's definition. If you also want Metabase's own serialization
export of a live, hand-tweaked instance (layout tweaks made in the UI that
the manifest doesn't capture, for example):
```bash
# Metabase serialization (v1.49+)
docker exec metabase java -jar /app/metabase.jar export /tmp/cgp-dash
docker cp metabase:/tmp/cgp-dash ./dashboards/metabase/export
```
