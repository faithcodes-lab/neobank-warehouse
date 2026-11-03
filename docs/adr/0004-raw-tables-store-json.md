# 4. Raw tables store each line as one JSON column

Date: 2026-11-01

Status: accepted. Answers the open question in [ADR 3](0003-imperfect-source-data.md) on typed
columns versus one JSON payload column.

Amended 2026-11-01: added how each file is loaded: the extra columns, the partition, and loading
twice changing nothing.

## Context

The load script puts the generator's files into BigQuery raw tables. Before writing it, the shape
of those tables has to be decided.

The architecture says raw holds exactly what arrived and is never edited, and that staging fixes
types. ADR 3 makes that harder than it sounds, because the source data is deliberately imperfect:
the card authorisation layout changes from v1 to v2, empty fields are sometimes absent and
sometimes null, and tap times carry local offsets.

There are two ways to store a line from a file:

- **typed columns**: each field gets its own column with a type, such as `amount_minor INTEGER`
  and `created_ts TIMESTAMP`, and the load puts each field in its column
- **one JSON column**: each line is stored whole, as it arrived, in a single `payload` column of
  BigQuery's JSON type, and staging picks the fields out

## Decision

All five raw tables store each line as one JSON column, called `payload`.

### Real scenarios

**The layout changes without warning.** On 15 August card authorisations start arriving with a
nested `amount` (ADR 3, issue 4). With typed columns, a table built for v1 has no column for it, and
at a real bank nobody told the warehouse, so the load fails. With one JSON column, it loads like any
other line and staging handles the new shape.

**A field nobody expected.** The card team later adds `entry_mode`. With typed columns, the load
either fails or, with `--ignore_unknown_values`, silently throws the field away, and it is gone from
raw for good. With one JSON column, it is kept until staging is ready to use it.

**Absent versus null.** With typed columns, a missing `decline_reason` and a `null` one both become
NULL, so raw can no longer show which one the service sent (ADR 3, issue 2). With one JSON column,
raw shows exactly what was sent.

**Local time offsets.** A tap arrives with `"created_ts": "2026-08-03T12:30:00+01:00"`. A
BigQuery `TIMESTAMP` stores the moment in UTC, 11:30, and drops the `+01:00`, so the fact that it
was a UK shop's local clock is lost on the way in. With one JSON column, the text is kept as it was
(ADR 3, issue 3).

### Why the same for all five

Customers, accounts, payments and merchants do not change layout today, but they could, and every
reason above applies to them too. One shape for every raw table also means the load script works
the same way for every source.

### What it looks like

| payload |
|---|
| `{"event_id": "abc-123", "account_id": "acc_0055", "amount_minor": 4520, "currency": "GBP", ...}` |
| `{"event_id": "def-456", "schema_version": 2, "account_id": "acc_0055", "amount": {"value_minor": 4520, "currency": "GBP"}, ...}` |

Staging picks fields out and gives them their types:

```sql
select
    json_value(payload, '$.event_id') as event_id,
    cast(json_value(payload, '$.amount_minor') as int64) as amount_minor
from raw.raw_card_authorisations
```

### How each file is loaded

Each source gets one table in the `raw` dataset, named `raw_` plus its folder, as in the
architecture diagram: `raw_customers`, `raw_accounts`, `raw_card_authorisations`, `raw_payments`
and `raw_merchants`. In BigQuery the full name is the dataset then the table, for example
`raw.raw_card_authorisations`.

**Extra columns.** Besides `payload`, the warehouse adds three columns of its own to every row, like
a label stuck on a parcel when it arrives. They describe the load, not the data.

| Column | Type | Example | Why |
|---|---|---|---|
| `payload` | JSON | the line from the file, untouched | this decision |
| `source_file` | STRING | `card_authorisations/2026-08-03.ndjson` | to trace any row back to the file it came from |
| `ingestion_date` | DATE | `2026-08-03` | the partition |
| `loaded_at` | TIMESTAMP | `2026-11-01T17:05:00Z` | when the load ran, so a reload can be told apart from an earlier one |

`ingested_ts` inside the payload is not used for any of these. It is part of the simulated data,
and snapshots and merchants do not have it.

**Partition.** Every table except merchants is partitioned by `ingestion_date`, which is the date
in the file name. Every row in a file gets the same date, so one file fills one partition.

| File | Its date means | Partition |
|---|---|---|
| `card_authorisations/2026-08-03.ndjson`, `payments/2026-08-03.ndjson` | the events that arrived that day, in UTC | 3 August |
| `customers/2026-08-03.ndjson`, `accounts/2026-08-03.ndjson` | the snapshot of that day | 3 August |
| `merchants.ndjson` | no date | not partitioned: one small file |

Partitioning by arrival rather than by when a tap happened means each day's arrivals go into a new
partition, and nothing already loaded ever has to move. A tap from 31 March that arrives on 2 April
goes into the 2 April partition.

**Loading twice changes nothing.** Each load replaces its own partition with the file's rows, so
loading the same file again puts back exactly the same rows. Loading once or ten times gives the same
result, which makes the load **idempotent**. Simply adding rows instead would put every row in twice
on a second load, and those copies could not be told apart from real redeliveries (ADR 3, issue 1).
A load only ever touches its own partition, and merchants, which have none, replace the whole
table.

This is not editing raw. A partition only ever holds exactly the file it belongs to.

**The load script.** `loader/load.py`, written in Python with Google's BigQuery library. For each
file it reads every line, wraps it with the three extra columns, and loads it into its partition.
It can be given one file, to load and check a single day, or no file, to load everything in
`data/`. It is run by hand for now. Because the load is idempotent, handing it to a scheduler later
is safe.

## Consequences

Raw really is exactly what arrived, so if staging gets something wrong, everything can be rebuilt
from raw without asking the sources to send it again.

A new or changed layout never stops the load. It shows up in staging instead, where tests on
staging columns, such as an amount that is never empty, catch a layout staging does not handle yet.

Staging has more work. Every field has to be picked out of the JSON and cast to its type, and
timestamps with offsets have to be converted to UTC there. That work belongs in staging anyway.

Querying raw directly is clumsier, because every field needs `json_value`. People are meant to
query staging and marts, not raw.

A type problem in the data, such as an amount sent as text, is caught when staging casts it rather
than when the file loads.

A plain `bq load` of NDJSON maps each top level field to its own column and cannot add the extra
columns, so the load is a Python script rather than `bq load` commands.

The partition for a day only holds what was in that day's file. If a second file for the same day
ever arrived, the load would need to change, because it would replace the first.

## Still open

- Running the load on a schedule, together with the generator and dbt, once it works by hand
