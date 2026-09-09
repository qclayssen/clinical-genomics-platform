-- Surrogate-keyed dimension of distinct pipeline versions seen in `runs`.
-- Mirrors the identity-keyed dim_pipeline_version table in db/schema.sql —
-- this dbt-managed copy lives in the `analytics` schema so it never
-- collides with the production `public.dim_pipeline_version` table that
-- Metabase actually reads from (see dbt/README.md for why both exist).

select
    row_number() over (order by pipeline_version) as pipeline_version_key,
    pipeline_version
from (
    select distinct pipeline_version
    from {{ ref('stg_runs') }}
) distinct_versions
