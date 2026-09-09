-- Thin 1:1 pass-through over the insert-only `samples` table (db/schema.sql).
-- No renaming/casting needed yet; kept as its own staging model so marts
-- never select from `public` tables directly (see dbt/README.md).

select
    sample_id,
    reference_build,
    created_at
from {{ source('cgp', 'samples') }}
