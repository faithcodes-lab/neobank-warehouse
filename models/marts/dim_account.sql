-- One row per version of each account (SCD2). The daily snapshots repeat every
-- account each day, so a new version starts only when status or closed_date
-- changes. The first version starts on opened_date, not the first snapshot,
-- because some new accounts arrive a day or two late (ADR 3) and their cards
-- can be used before then. valid_to is the day the next version starts, and is
-- empty on the current version.

with snapshots as (

    select * from {{ ref('stg_accounts') }}

),

with_previous as (

    select
        *,
        lag(status) over (partition by account_id order by snapshot_date) as previous_status,
        lag(closed_date) over (partition by account_id order by snapshot_date) as previous_closed_date
    from snapshots

),

flagged as (

    -- closed_date is empty until the account closes, so it is compared with
    -- is distinct from, which treats two empty values as the same
    select
        *,
        previous_status is null
            or status != previous_status
            or closed_date is distinct from previous_closed_date as is_new_version
    from with_previous

),

numbered as (

    select
        *,
        countif(is_new_version) over (partition by account_id order by snapshot_date) as version_number
    from flagged

),

versions as (

    select
        account_id,
        version_number,
        customer_id,
        account_type,
        currency,
        status,
        opened_date,
        closed_date,
        min(snapshot_date) as first_seen
    from numbered
    group by account_id, version_number, customer_id, account_type, currency, status, opened_date, closed_date

)

select
    account_id || '|' || cast(version_number as string) as account_key,
    account_id,
    version_number,
    customer_id,
    account_type,
    currency,
    status,
    opened_date,
    closed_date,
    case when version_number = 1 then opened_date else first_seen end as valid_from,
    lead(first_seen) over (partition by account_id order by version_number) as valid_to,
    lead(first_seen) over (partition by account_id order by version_number) is null as is_current
from versions