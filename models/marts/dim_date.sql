-- One row per calendar day. No source sends a calendar, so it is generated
-- from a date range wide enough to cover every date in the data: the first
-- signups in 2020 through to the end of 2026.

with days as (

    select date_day
    from unnest(generate_date_array('2020-01-01', '2026-12-31')) as date_day

)

select
    date_day,
    extract(year from date_day) as year,
    extract(quarter from date_day) as quarter,
    extract(month from date_day) as month,
    format_date('%B', date_day) as month_name,
    extract(day from date_day) as day_of_month,
    -- BigQuery counts 1 as Sunday and 7 as Saturday
    extract(dayofweek from date_day) as day_of_week,
    format_date('%A', date_day) as day_name,
    extract(dayofweek from date_day) in (1, 7) as is_weekend,
    date_trunc(date_day, week(monday)) as week_start,
    date_trunc(date_day, month) as month_start
from days