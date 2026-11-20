-- One row per version of each customer (SCD2). The daily snapshots repeat every
-- customer each day, so a new version starts only when country or closed_date
-- changes. valid_to is the day the next version starts, and is empty on the
-- current version.

with snapshots as (

    select * from {{ ref('stg_customers') }}

),

with_previous as (

    select
        *,
        lag(country) over (partition by customer_id order by snapshot_date) as previous_country,
        lag(closed_date) over (partition by customer_id order by snapshot_date) as previous_closed_date
    from snapshots

),

flagged as (

    -- closed_date is empty until the customer leaves, so it is compared with
    -- is distinct from, which treats two empty values as the same
    select
        *,
        previous_country is null
            or country != previous_country
            or closed_date is distinct from previous_closed_date as is_new_version
    from with_previous

),

numbered as (

    select
        *,
        countif(is_new_version) over (partition by customer_id order by snapshot_date) as version_number
    from flagged

),

versions as (

    select
        customer_id,
        version_number,
        full_name,
        country,
        date_of_birth,
        signup_date,
        closed_date,
        min(snapshot_date) as valid_from
    from numbered
    group by customer_id, version_number, full_name, country, date_of_birth, signup_date, closed_date

)

select
    customer_id || '|' || cast(version_number as string) as customer_key,
    customer_id,
    version_number,
    full_name,
    country,
    date_of_birth,
    signup_date,
    closed_date,
    valid_from,
    lead(valid_from) over (partition by customer_id order by valid_from) as valid_to,
    lead(valid_from) over (partition by customer_id order by valid_from) is null as is_current
from versions