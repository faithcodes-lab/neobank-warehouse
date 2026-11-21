-- One row per account per day, with the money that settled that day and the
-- running balance at the end of it. The data has no deposits and no opening
-- balance, so the balance starts at 0 on 1 July (or the opening day, if later)
-- and only moves with card payments: refunds add, captures take away. Rows carry
-- on after an account closes, because some payments settle after closing.
-- The balance can be added up across accounts on one day, but never across days.

with accounts as (

    select account_id, currency, opened_date, closed_date
    from {{ ref('dim_account') }}
    where is_current

),

payments as (

    select * from {{ ref('stg_payments') }}

),

data_end as (

    select max(date(created_at)) as last_day
    from payments

),

account_days as (

    -- every account paired with every day from its start to the end of the data
    select
        a.account_id,
        a.currency,
        a.closed_date,
        d.date_day as balance_date
    from accounts as a
    cross join data_end as e
    inner join {{ ref('dim_date') }} as d
        on d.date_day between greatest(a.opened_date, date '2026-07-01') and e.last_day

),

daily_movements as (

    select
        account_id,
        date(created_at) as balance_date,
        coalesce(sum(if(settlement_type = 'refund', amount_minor, null)), 0) as money_in_minor,
        coalesce(sum(if(settlement_type = 'capture', amount_minor, null)), 0) as money_out_minor
    from payments
    group by account_id, balance_date

)

select
    d.account_id || '|' || cast(d.balance_date as string) as account_day_key,
    d.account_id,
    d.balance_date,
    d.currency,
    d.closed_date is null or d.balance_date < d.closed_date as is_open,
    coalesce(m.money_in_minor, 0) as money_in_minor,
    coalesce(m.money_out_minor, 0) as money_out_minor,
    sum(coalesce(m.money_in_minor, 0) - coalesce(m.money_out_minor, 0))
        over (partition by d.account_id order by d.balance_date) as settled_balance_minor
from account_days as d
left join daily_movements as m
    on m.account_id = d.account_id
    and m.balance_date = d.balance_date