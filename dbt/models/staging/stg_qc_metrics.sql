-- Thin pass-through over the insert-only `qc_metrics` table (db/schema.sql).
-- Grain: one row per run (1:1 with stg_runs).

select
    run_pk,
    percent_duplication,
    snp_precision,
    snp_recall,
    snp_f1,
    n_variants
from {{ source('cgp', 'qc_metrics') }}
