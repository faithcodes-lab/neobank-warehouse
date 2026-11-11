-- One row per payment event from raw_payments, with fields picked out of the JSON
-- payload and given their types. Timestamps are converted to UTC and duplicates removed.

with source as (

    select * from {{ source('raw', 'raw_payments') }}

),

typed as (

    select
        json_value(payload, '$.event_id') as event_id,
        json_value(payload, '$.authorisation_event_id') as authorisation_event_id,
        json_value(payload, '$.account_id') as account_id,
        json_value(payload, '$.merchant_id') as merchant_id,
        cast(json_value(payload, '$.amount_minor') as int64) as amount_minor,
        json_value(payload, '$.currency') as currency,
        json_value(payload, '$.settlement_type') as settlement_type,
        timestamp(json_value(payload, '$.created_ts')) as created_at,
        timestamp(json_value(payload, '$.ingested_ts')) as ingested_at,
        source_file,
        ingestion_date
    from source

),

deduplicated as (

    -- A redelivered event keeps its event_id and arrives later.
    -- Keep the first arrival. This looks across every day, because a copy can
    -- land in the next day's file.
    select *
    from typed
    qualify row_number() over (partition by event_id order by ingested_at) = 1

)

select * from deduplicated