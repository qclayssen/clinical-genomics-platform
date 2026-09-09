-- Surrogate-keyed dimension of distinct variant callers seen in `runs`.
-- Analytics-schema counterpart to db/schema.sql's public.dim_caller table.

select
    row_number() over (order by caller) as caller_key,
    caller
from (
    select distinct caller
    from {{ ref('stg_runs') }}
) distinct_callers
