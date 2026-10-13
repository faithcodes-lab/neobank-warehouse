# 2. Payment, customer and account payloads

Date: 2026-10-07

Status: accepted. Completes the contract started in [ADR 1](0001-source-event-contract.md), which
settled the service split and the card authorisation event.

## Context

ADR 1 left three payloads unspecified: the payment settlement event, and the customer and account
snapshots. The generator cannot be written until they are decided.

## Payment settlement event

```
event_id                  unique per event
authorisation_event_id    the authorisation this settles
account_id
merchant_id
amount_minor              what actually moved, not what was authorised
currency
settlement_type           capture or refund
created_ts                when settlement happened
ingested_ts               when the warehouse received it
```

### Linking settlement to authorisation

Settlement carries `authorisation_event_id` pointing back at the original tap. That gives a clean
join and lets me compare the authorised amount to the settled one.

Real payment systems are messier than this. The settlement message originates from the merchant's
bank and travels through the card network, and the reference back to the authorisation sometimes
arrives wrong or missing. Banks then match on best guess instead: same card, same merchant, a
similar amount, within a few days. It is a real operational problem with a name, auth to clearing
matching, and teams own it.

I am using the clean reference on purpose. Rebuilding payment network matching would be a
project in itself and it is not what this warehouse is for. Worth recording that I know the
simplification is there rather than leaving it unsaid.

### settlement_type, and why status is derived

`status` on a transaction is not sent by any service. Nothing upstream knows it. It gets worked out
in the warehouse from whether a settlement turned up:

| Authorisation | Settlement | Status |
|---|---|---|
| exists | none yet | pending |
| exists | capture | settled |
| exists | capture then refund | reversed |

That rule needs `settlement_type` to work, because a refund is itself a settlement event. Money
moving back is still money moving, so without a type field both the original charge and the refund
would look like captures and both would read as settled.

`capture` is the industry term for a settlement that claims the authorised money, so I am using the
real word rather than inventing one.

This is the first derived column in the warehouse, and it is a good example of what the marts
layer is for. Staging tidies what arrived. Marts works out things nobody sent.

## Customer snapshot

```
snapshot_date     the business day this file represents
extracted_at      when the extract job actually ran
customer_id
full_name
date_of_birth
country
signup_date
closed_date       null while they are still a customer
```

## Account snapshot

```
snapshot_date
extracted_at
account_id
customer_id
account_type      current or savings
currency
opened_date
closed_date       null while open
status            open or closed
```

### Two dates on a snapshot

`snapshot_date` is logical: which day's state this represents. It is what I join on, what I compare
consecutive files by, and what dbt snapshots use to build validity ranges.

`extracted_at` is physical: when the job actually ran. These routinely differ, because the snapshot
for 1 March is produced at 2am on 2 March once the day has closed. If only one survived I would keep
`snapshot_date`, since the logical day is what the data means, but `extracted_at` is what I will
want the first time a file is missing or a job runs twice.

It is the same pattern as `created_ts` and `ingested_ts` on the events. One timestamp for when
something was true, one for when it was received.

### Balance is not an account attribute

The account snapshot deliberately excludes the balance, even though it is obviously part of an
account's daily state.

Balance changes constantly, so it is not a stable descriptive attribute, and dimensions hold things
that change slowly. It belongs in `fct_account_daily_balance` instead.

It is also not a simple measure. Summing one account's balance across 31 days produces a
number that never existed. Summing every account's balance on a single day produces total customer
deposits, which is a real figure and is what a regulatory return asks for. So it can be aggregated
across accounts but not across time, which makes it semi additive.

That needs documenting on the model, because a BI tool will sum it over time by default and report
total deposits ten times too high. The model description has to say not to.

## Consequences

Comparing authorisation to settlement is now possible, which is the point, and it means spend has
to be reported from settlements rather than authorisations. Authorisations overstate fuel and
understate tipped meals.

Transaction status depends on a join between two event streams rather than on a column, so it is
only correct once both have loaded. A transaction looks pending until its settlement arrives, which
is accurate rather than a bug, but it means the number of pending transactions is a function of how
recently the pipeline ran.

The snapshots are wide and mostly unchanged day to day. A year of daily customer files is 365 near
identical copies of each customer. That is a lot of repeated data, but it is what makes dbt
snapshots work, and at this volume the storage cost does not matter.

## Still open

Nothing from the contract. The generator can be written now.

Not decided yet, and deliberately left for when a model needs them: whether the ledger is modelled
as double entry, and which balance `fct_account_daily_balance` holds. Available balance and settled
balance are different numbers and the difference matters for anything regulatory.
