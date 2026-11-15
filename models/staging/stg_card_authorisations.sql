-- One row per card authorisation from raw_card_authorisations. Two layouts arrive mixed:
-- v1 has amount_minor and currency at the top level, and v2 (schema_version 2) moves
-- them inside an amount object. Both are read into the same columns. Timestamps are
-- converted to UTC and duplicates removed.

with source as (

    select * from {{ source('raw', 'raw_card_authorisations') }}

),

typed as (

    select
        json_value(payload, '$.event_id') as event_id,
        json_value(payload, '$.account_id') as account_id,
        json_value(payload, '$.merchant_id') as merchant_id,
        json_value(payload, '$.mcc') as mcc,
        coalesce(
            cast(json_value(payload, '$.amount_minor') as int64),
            cast(json_value(payload, '$.amount.value_minor') as int64)
        ) as amount_minor,
        coalesce(
            json_value(payload, '$.currency'),
            json_value(payload, '$.amount.currency')
        ) as currency,
        json_value(payload, '$.outcome') as outcome,
        -- v1 sends null when approved, v2 leaves the field out. Both read as null here.
        json_value(payload, '$.decline_reason') as decline_reason,
        coalesce(cast(json_value(payload, '$.schema_version') as int64), 1) as schema_version,
        timestamp(json_value(payload, '$.created_ts')) as created_at,
        timestamp(json_value(payload, '$.ingested_ts')) as ingested_at,
        source_file,
        ingestion_date
    from source

),

deduplicated as (

    -- A redelivered event keeps its event_id and arrives later.
    -- Keep the first arrival, looking across every day.
    select *
    from typed
    qualify row_number() over (partition by event_id order by ingested_at) = 1

)

select * from deduplicated
