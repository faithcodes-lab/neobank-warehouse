-- One row per account per snapshot day from raw_accounts. Each daily file is a full
-- snapshot, so an account appears once a day by design. These are not duplicates.
-- There is no snapshot for 21 August, and some new accounts first appear a day or two
-- after they opened (ADR 3). Staging keeps what arrived and does not fill these gaps.

with source as (

    select * from {{ source('raw', 'raw_accounts') }}

),

typed as (

    select
        date(json_value(payload, '$.snapshot_date')) as snapshot_date,
        json_value(payload, '$.account_id') as account_id,
        json_value(payload, '$.customer_id') as customer_id,
        json_value(payload, '$.account_type') as account_type,
        json_value(payload, '$.currency') as currency,
        json_value(payload, '$.status') as status,
        date(json_value(payload, '$.opened_date')) as opened_date,
        date(json_value(payload, '$.closed_date')) as closed_date,
        timestamp(json_value(payload, '$.extracted_at')) as extracted_at,
        source_file,
        ingestion_date
    from source

)

select * from typed