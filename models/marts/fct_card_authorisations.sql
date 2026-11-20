-- One row per card authorisation, approved or declined. The keys link to
-- dim_merchant and dim_date (and to dim_account once it is built). An
-- authorisation is not spend: money only moves when a payment settles it.

with authorisations as (

    select * from {{ ref('stg_card_authorisations') }}

)

select
    event_id as authorisation_id,
    account_id,
    merchant_id,
    date(created_at) as authorised_date,
    created_at as authorised_at,
    ingested_at,
    amount_minor,
    currency,
    outcome,
    outcome = 'approved' as is_approved,
    decline_reason
from authorisations