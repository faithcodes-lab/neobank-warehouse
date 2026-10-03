# neobank-warehouse

A dimensional data warehouse for a retail bank, built on BigQuery and dbt.

Retail banking runs on separate backend services: one owns customers, one owns accounts, one owns
card authorisation, one owns the ledger. Each is tuned for transactional throughput, which makes
them the wrong place to answer questions. Querying the card service to produce a spend report
competes with the traffic that approves payments.

This warehouse is the analytical copy. Service events land unmodified, then get modelled into a
star schema that supports reporting, finance and regulatory use cases.

## Architecture

```
service events (NDJSON)
        |
        v
   raw  append only, never edited, partitioned by ingestion date
        |
        v
staging  one model per source: renamed, typed, payloads flattened, duplicates resolved
        |
        v
  marts  conformed dimensions and facts
```

Each layer has exactly one responsibility. Raw is the audit trail and the rebuild point: if a
transformation turns out to be wrong, the whole warehouse can be rebuilt from it without going
back to the source systems. Staging is mechanical and holds no business logic. Marts is where
modelling decisions live.

## Source data

A generator produces events in the shape real services emit them, which means imperfect by
design:

- the same event delivered more than once, with a later ingestion timestamp
- events arriving out of order and after the period they belong to
- a payload schema that changes partway through the history, v1 and v2 coexisting
- optional and nullable fields that are absent rather than empty
- timestamps in mixed timezone offsets
- occasional referential gaps, where a transaction names an account that arrives later

A pipeline that only works against clean input is not a pipeline. Handling this is the substance
of the project rather than an edge case bolted on at the end.

## Dimensional model

| Model | Grain |
|---|---|
| `dim_customer` | one row per customer per version |
| `dim_account` | one row per account per version |
| `dim_merchant` | one row per merchant |
| `dim_date` | one row per calendar day |
| `fct_transactions` | one row per transaction |
| `fct_card_authorisations` | one row per authorisation attempt |
| `fct_account_daily_balance` | one row per account per day |

`dim_customer` and `dim_account` are slowly changing type 2. When an account changes product or
status, the existing row is closed off with a validity end date and a new row opens. Overwriting
in place would be simpler, and it would silently rewrite history: a report run against last
quarter would reflect this quarter's attributes. Type 2 costs more storage and more join
complexity, and it is the only way to answer what a figure looked like as at a past date.

Every model declares its grain, carries a description, and has at least one test.

## Testing

Schema level tests cover uniqueness, nullability and referential integrity. Beyond those, tests
assert things that are true of the business rather than of the table:

- ledger entries for a transaction sum to zero, because double entry bookkeeping requires it
- an authorisation always precedes its settlement
- no transaction is dated in the future

A test suite that only checks for nulls will pass while the numbers are wrong.

## Stack

BigQuery, dbt core 1.12 with the BigQuery adapter, Python 3.12, GitHub Actions.

## Repository conventions

One branch per unit of work, everything through a pull request. Design decisions are recorded as
ADRs in `docs/adr/`, including the ones that were reversed.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the rest.
