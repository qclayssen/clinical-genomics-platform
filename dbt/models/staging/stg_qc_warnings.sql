-- Thin pass-through over the insert-only `qc_warnings` table (db/schema.sql).
-- Grain: one row per warning check per run — aggregated to run grain in
-- fct_run (count of warn/fail rows per run).

select
    run_pk,
    overall_status
from {{ source('cgp', 'qc_warnings') }}
