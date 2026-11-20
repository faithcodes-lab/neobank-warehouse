-- One row per approved card authorisation, with what happened to the money.
-- Payments are squashed to one row per authorisation before joining, so a
-- capture and its refund do not turn one transaction into two rows. Status is
-- worked out from which payments have arrived, because no source sends it.
-- Declined taps are left out, since no money was ever going to move. They are
-- in fct_card_authorisations.

with authorisations as (

    select * from {{ ref('stg_card_authorisations') }}
    where outcome = 'approved'

),

payments as (

    select * from {{ ref('stg_payments') }}

),

payments_per_authorisation as (

    select
        authorisation_event_id,
        countif(settlement_type = 'capture') as captures,
        countif(settlement_type = 'refund') as refunds,
        sum(if(settlement_type = 'capture', amount_minor, null)) as settled_amount_minor,
        sum(if(settlement_type = 'refund', amount_minor, null)) as refunded_amount_minor,
        min(if(settlement_type = 'capture', created_at, null)) as settled_at,
        min(if(settlement_type = 'refund', created_at, null)) as refunded_at
    from payments
    group by authorisation_event_id

)

select
    a.event_id as transaction_id,
    a.account_id,
    a.merchant_id,
    date(a.created_at) as authorised_date,
    a.created_at as authorised_at,
    a.currency,
    a.amount_minor as authorised_amount_minor,
    p.settled_amount_minor,
    p.refunded_amount_minor,
    p.settled_at,
    p.refunded_at,
    -- reversed is checked first, because a reversed transaction has a capture too
    case
        when p.refunds > 0 then 'reversed'
        when p.captures > 0 then 'settled'
        else 'pending'
    end as status
from authorisations as a
left join payments_per_authorisation as p
    on p.authorisation_event_id = a.event_id