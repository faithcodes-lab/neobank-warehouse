# 1. Source event contract

Date: 2026-10-06

Status: accepted, partially. The card authorisation event is settled. The payment, customer and
account payloads still need working through.

## Context

The generator stands in for a bank's backend services, so before writing it I need to decide what
those services emit. Changing my mind afterwards means rewriting the generator and every staging
model downstream of it, so the decision comes first.

Two things needed settling: which services exist, and whether each one hands over a stream of
events or a snapshot of its current state.

## Decision

Four services plus one reference table:

| Source | Delivers |
|---|---|
| customer service | daily snapshot of every customer |
| account service | daily snapshot of every account |
| card service | authorisation events |
| payment service | settlement events |
| merchant | reference lookup, changes rarely |

### Snapshots for customer and account

A warehouse usually receives a daily extract of current state for dimensions rather than the
underlying change events, because reconstructing current state by replaying a long event history
is slow and expensive. So that is what I am simulating.

The consequence is that a change is not announced. If a customer moves from Ireland to France, I
find out by noticing that today's file differs from yesterday's. dbt has a snapshot feature that
does that comparison and builds the type 2 history from it, which is what I will use.

### Events for card and payment

Authorisation and settlement are genuinely separate events, often days apart, and they can carry
different amounts. Collapsing them into one record would lose that, so each is its own event.

### Merchant is reference data, not events

The bank does not manage merchants. Tesco is not a customer of the bank. What arrives with a card
authorisation is a category code and an untidy merchant string from the payment network, something
like `TESCO STORES 3456 BRISTOL GB`. The clean name and the friendly category are things the bank
works out afterwards and maintains itself.

That makes merchant data different in kind from the rest. It changes slowly, nothing emits it, and
nobody should be alarmed if it is unchanged for a week. Transactions going quiet for an hour is an
incident. The freshness checks have to differ accordingly.

## Card authorisation event

```
event_id          unique per event, the key for deduplication
account_id        whose card was used
merchant_id       for joining to merchant reference data
mcc               four digit merchant category code, 5411 is groceries
amount_minor      minor units, so 4520 is 45.20
currency          GBP, EUR or USD
outcome           approved or declined
decline_reason    populated only when declined
created_ts        when the tap happened
ingested_ts       when the warehouse received it
```

`event_id` is the one field the project cannot work without. Services deliver at least once, so the
same authorisation can arrive twice. Two coffees bought seconds apart at the same price are
indistinguishable from one duplicated coffee unless each event carries its own id.

`currency` matters more than it looks. The bank has customers in Ireland and France, so summing
mixed currencies without converting produces a number that means nothing.

The two timestamps exist because they answer different questions. A transaction at 23:50 on 31
March that arrives at 00:30 on 2 April belongs in March by `created_ts`, because that is when the
customer spent the money, and in April by `ingested_ts`, because that is when the warehouse knew
about it. A March report run on 1 April was short by one transaction and nobody was at fault. Both
timestamps are needed to explain that afterwards, which is also why the raw tables are partitioned
by ingestion date: whatever arrives today lands in today's partition and nothing already written
has to be rewritten.

## Consequences

Dimensions cost more work. Reconstructing history from consecutive snapshots is harder than being
handed change events, and it depends on dbt snapshots running on a schedule. Miss a day and that
day's changes are invisible, because there is no event to replay.

`dim_customer` and `dim_account` hold one row per entity per version rather than one row per
entity. Anything joining to them has to pick the version that was valid at the right date, which
is easy to get wrong and needs testing.

Authorisation amounts cannot be treated as spend. Settlement is the real figure, and it can
legitimately exceed the authorisation: restaurants settle above the authorised amount to cover
tips, within a tolerance of roughly twenty percent. A test asserting that settlement never exceeds
authorisation would fail on every tipped meal, so the data quality rule has to allow for it.

## Still open

The payment settlement event, the customer snapshot and the account snapshot payloads are not yet
specified. Same approach: work out what each one needs, then write it down here before the
generator is built.
