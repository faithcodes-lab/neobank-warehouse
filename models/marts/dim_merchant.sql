-- One row per merchant, for looking up who a card tap or payment was with.
-- The merchant list has no history, so this is a straight copy of staging
-- without the loading columns.

with merchants as (

    select * from {{ ref('stg_merchants') }}

)

select
    merchant_id,
    merchant_name,
    category,
    mcc,
    country
from merchants