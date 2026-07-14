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
# 3. In Metabase, add the Postgres DB, then create one Native Question per query below.
```

All cards read from the `v_run_summary` view (see `db/schema.sql`).

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

## Exporting for version control

After building the dashboard, export it so it lives in git:
```bash
# Metabase serialization (v1.49+)
docker exec metabase java -jar /app/metabase.jar export /tmp/cgp-dash
docker cp metabase:/tmp/cgp-dash ./dashboards/metabase/export
```
