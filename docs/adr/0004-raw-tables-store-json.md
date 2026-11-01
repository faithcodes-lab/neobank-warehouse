# 4. Raw tables store each line as one JSON column

Date: 2026-11-01

Status: accepted. Answers the open question in [ADR 3](0003-imperfect-source-data.md) on typed
columns versus one JSON payload column.

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
from raw_card_authorisations
```

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

A plain `bq load` of NDJSON maps each top level field to its own column, so loading a whole line
into one column needs a different load setup. That is decided with the load script.

## Still open

- The columns the warehouse adds to each row itself, such as the source file name and when it was
  loaded
- How the ingestion date partition is set for each row
- How the load is made idempotent, so loading the same file twice changes nothing
