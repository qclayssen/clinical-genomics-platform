-- Thin pass-through over the insert-only `runs` table (db/schema.sql).
-- Grain: one row per pipeline run.

select
    id                as run_pk,
    run_id,
    sample_id,
    pipeline_version,
    git_commit,
    caller,
    started_at,
    exported_at,
    validation_pass
from {{ source('cgp', 'runs') }}
