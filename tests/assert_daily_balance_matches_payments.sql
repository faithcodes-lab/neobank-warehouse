-- Every settled payment should land on exactly one day of the balance table,
-- so the money in and out there must match the payments, account by account.
-- Returns the accounts where it does not.

with from_payments as (

    select
        account_id,
        sum(if(settlement_type = 'refund', amount_minor, -amount_minor)) as net_minor
    from {{ ref('stg_payments') }}
    group by account_id

),

from_balances as (

    select
        account_id,
        sum(money_in_minor - money_out_minor) as net_minor
    from {{ ref('fct_account_daily_balance') }}
    group by account_id

)

select
    p.account_id,
    p.net_minor as payments_net_minor,
    b.net_minor as balances_net_minor
from from_payments as p
left join from_balances as b
    on b.account_id = p.account_id
where b.net_minor is null
    or b.net_minor != p.net_minor