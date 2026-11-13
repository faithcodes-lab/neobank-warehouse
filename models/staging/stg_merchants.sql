-- One row per merchant from raw_merchants, with fields picked out of the JSON payload.
-- mcc is a category code, not a number, so it stays as text.

with source as (

    select * from {{ source('raw', 'raw_merchants') }}

),

typed as (

    select
        json_value(payload, '$.merchant_id') as merchant_id,
        json_value(payload, '$.merchant_name') as merchant_name,
        json_value(payload, '$.category') as category,
        json_value(payload, '$.mcc') as mcc,
        json_value(payload, '$.country') as country,
        source_file
    from source

)

select * from typed
