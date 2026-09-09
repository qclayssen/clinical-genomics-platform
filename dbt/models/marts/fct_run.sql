-- Analytics-schema counterpart to db/schema.sql's public.fact_run
-- materialized view. Grain: one row per pipeline run. Built the
-- dbt/analytics-engineering way (staged sources -> dimensions -> fact with
-- ref()s and generic tests) alongside the hand-rolled SQL warehouse that
-- Metabase actually reads from in production — see dbt/README.md.

with warning_counts as (
    select
        run_pk,
        count(*) filter (where overall_status = 'warn') as n_warn,
        count(*) filter (where overall_status = 'fail') as n_fail
    from {{ ref('stg_qc_warnings') }}
    group by run_pk
)

select
    r.run_pk as run_key,
    r.run_id,
    r.sample_id,
    r.pipeline_version,
    pv.pipeline_version_key,
    r.caller,
    c.caller_key,
    date_trunc('day', r.started_at)::date as date_key,
    r.started_at,
    r.exported_at,
    extract(epoch from (r.exported_at - r.started_at)) / 60.0 as turnaround_min,
    r.validation_pass,
    q.snp_precision,
    q.snp_recall,
    q.snp_f1,
    q.percent_duplication,
    q.n_variants,
    coalesce(wc.n_warn, 0) as n_warn,
    coalesce(wc.n_fail, 0) as n_fail
from {{ ref('stg_runs') }} r
join {{ ref('stg_qc_metrics') }} q on q.run_pk = r.run_pk
join {{ ref('dim_pipeline_version') }} pv on pv.pipeline_version = r.pipeline_version
join {{ ref('dim_caller') }} c on c.caller = r.caller
left join warning_counts wc on wc.run_pk = r.run_pk
