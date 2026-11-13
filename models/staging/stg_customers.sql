
-- One row per customer per snapshot day from raw_customers. Each daily file is a full
-- snapshot, so a customer appears once a day by design. These are not duplicates.

with source as (

    select * from {{ source('raw', 'raw_customers') }}

),

typed as (

    select
        date(json_value(payload, '$.snapshot_date')) as snapshot_date,
        json_value(payload, '$.customer_id') as customer_id,
        json_value(payload, '$.full_name') as full_name,
        json_value(payload, '$.country') as country,
        date(json_value(payload, '$.date_of_birth')) as date_of_birth,
        date(json_value(payload, '$.signup_date')) as signup_date,
        date(json_value(payload, '$.closed_date')) as closed_date,
        timestamp(json_value(payload, '$.extracted_at')) as extracted_at,
        source_file,
        ingestion_date
    from source

)

select * from typed