-- Date dimension derived from run start dates. Analytics-schema counterpart
-- to db/schema.sql's public.dim_date view.

select distinct
    date_trunc('day', started_at)::date as date_key,
    extract(isoyear from started_at)::int as iso_year,
    extract(week from started_at)::int as iso_week,
    extract(dow from started_at)::int as day_of_week,
    trim(to_char(started_at, 'Day')) as day_name
from {{ ref('stg_runs') }}
where started_at is not null
