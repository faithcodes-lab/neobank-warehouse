# Architecture

Two diagrams. The first shows the whole pipeline, from something happening in a bank through to
the tables people query. The second shows the card payment lifecycle, which is the thing that
makes the modelling awkward.

All are written in Mermaid, which GitHub renders in the browser.

## What actually runs

In a real bank, data appears because people do things. Someone taps a card, someone opens an
account, a shop claims its money. Backend services record each of those.

There are no real people here and no real services. One Python program stands in for the lot,
writing files that look like what those services would have sent.

```mermaid
flowchart TD
    subgraph world["1. What happens in a real bank"]
        w1["a customer signs up<br/>or changes their address"]
        w2["someone opens or closes<br/>an account"]
        w3["a customer taps their card<br/>at a till"]
        w4["a shop claims the money<br/>it is owed, in a daily batch"]
    end

    subgraph svc["2. In a real bank, a service records it"]
        c1["customer service"]
        c2["account service"]
        c3["card service"]
        c4["payment service"]
        c5["merchant list<br/>built up by the bank"]
    end

    gen["3. This project has none of those services.<br/>One Python generator produces what they would have sent."]

    subgraph files["4. NDJSON files on disk"]
        f1["customers<br/>daily snapshot"]
        f2["accounts<br/>daily snapshot"]
        f3["card authorisations<br/>events"]
        f4["payments<br/>events"]
        f5["merchants<br/>no date"]
    end

    load["5. bq load"]

    subgraph raw["6. BigQuery raw, never edited"]
        r1[("raw_customers")]
        r2[("raw_accounts")]
        r3[("raw_card_authorisations")]
        r4[("raw_payments")]
        r5[("raw_merchants")]
    end

    dbtrun["7. dbt run"]

    subgraph staging["8. staging, views, no storage"]
        g1["stg_customers"]
        g2["stg_accounts"]
        g3["stg_card_authorisations"]
        g4["stg_payments"]
        g5["stg_merchants"]
    end

    subgraph marts["9. marts, tables people query"]
        d1[("dim_customer<br/>SCD2")]
        d2[("dim_account<br/>SCD2")]
        d3[("dim_merchant")]
        d4[("dim_date<br/>generated, no source")]
        t1[("fct_card_authorisations")]
        t2[("fct_transactions")]
        t3[("fct_account_daily_balance")]
    end

    w1 --> c1
    w2 --> c2
    w3 --> c3
    w4 --> c4

    c1 & c2 & c3 & c4 & c5 --> gen
    gen --> f1 & f2 & f3 & f4 & f5

    f1 & f2 & f3 & f4 & f5 --> load
    load --> r1 & r2 & r3 & r4 & r5
    r1 & r2 & r3 & r4 & r5 --> dbtrun

    dbtrun --> g1 & g2 & g3 & g4 & g5

    g1 --> d1
    g2 --> d2
    g5 --> d3
    g3 --> t1
    g3 --> t2
    g4 --> t2
    g2 --> t3
    g4 --> t3
```

Steps 3 and 4 happen on a laptop. Everything from step 5 onwards is BigQuery, which is the only
cloud service this project uses.

| Step | What happens | What runs it |
|---|---|---|
| 1 | a customer taps a card, signs up, opens an account, or a shop claims its money | the real world |
| 2 | the service that owns that area records it | a real bank. This project has none |
| 3 | one Python generator produces what those services would have sent | a laptop |
| 4 | the generator writes files. Customer and account write a full daily snapshot, card and payment write one line per event | a laptop |
| 5 | `bq load` sends each file over | a BigQuery **load job**, reading the file and writing into storage |
| 6 | raw tables, exactly what arrived, never edited | BigQuery **storage**. Partitioning is a storage feature, it decides the physical layout |
| 7 | `dbt run` builds everything above raw | BigQuery **query jobs**. The SQL runs on Google's machines, not the laptop |
| 8 | staging views rename, type and remove duplicates | **metadata only**. A view is a saved query, so it takes no storage |
| 9 | marts, the tables people query | BigQuery **storage**, written by the query jobs that built them |

Every operation is recorded as a job, and `INFORMATION_SCHEMA.JOBS` holds a row for each one. The
`query-comment` setting in `dbt_project.yml` labels each job with the model that produced it, so
usage can later be attributed per model rather than appearing as one anonymous total.

Three things you run, in order:

1. `python generator/generate.py` writes the files
2. `bq load` puts them in BigQuery
3. `dbt run` builds everything on top

Worth noticing:

**Raw to staging is one to one.** Five tables in, five out. Staging only tidies, it never combines.

**Staging to marts is not.** Five go in, seven come out, and some cross over. This is where the
shape changes.

**`fct_transactions` has two arrows into it.** It needs authorisations and settlements both,
because transaction status is worked out by checking whether a settlement arrived. No source sends
that column.

**`dim_date` has no arrow in.** It is generated from a date range, because nothing upstream emits
a calendar.

## Card payment lifecycle

One card tap produces two events, days apart, possibly for different amounts. This is why
`fct_transactions` needs two sources.

```mermaid
sequenceDiagram
    autonumber
    participant C as Customer
    participant T as Terminal
    participant N as Card network
    participant B as Bank
    participant W as Warehouse

    Note over C,W: Day 1, 09:14. Authorisation.

    C->>T: taps card, 45.20
    T->>N: can this card pay?
    N->>B: can this card pay?
    B->>B: check balance, fraud rules, limits
    B-->>N: approved
    N-->>T: approved
    T-->>C: receipt printed
    B->>B: hold 45.20 against available balance
    B->>W: authorisation event

    Note over C,B: No money has moved. 45.20 is reserved, not taken.

    Note over C,W: Day 3, 22:00. Settlement.

    T->>N: merchant submits the day's batch
    N->>B: settlement, 45.20, capture
    B->>B: release the hold, move the money
    B->>W: settlement event

    W->>W: join the two, work out the status
```

### Why this causes problems

**Authorisation is not spend.** A hold can be released without money ever moving, if the merchant
abandons it or it expires. Reporting spend from authorisations overstates it.

**Settlement can differ from authorisation.** A restaurant authorises 40.00 and settles 48.00 once
a tip is added. A pay at pump petrol station authorises 100.00 and settles 62.00. Card networks
allow settlement above the authorised amount by roughly twenty percent, so a test asserting
settlement never exceeds authorisation would fail on every tipped meal.

**Status is derived, not sent.** Nothing upstream knows whether a transaction is pending or
settled, because that depends on whether a second event has turned up yet.

| Authorisation | Settlement | Status |
|---|---|---|
| exists | none yet | pending |
| exists | capture | settled |
| exists | capture then refund | reversed |

**Two timestamps are needed.** `created_ts` is when it happened, `ingested_ts` is when the
warehouse received it. A transaction at 23:50 on 31 March arriving at 00:30 on 2 April counts as
March by the first and April by the second. Both are correct, for different questions.

## Why three layers

**raw** holds exactly what arrived and is never edited. If a transformation turns out to be wrong,
everything downstream is rebuilt from here rather than asking the source systems to send it again.

**staging** renames columns, fixes types, and removes duplicate deliveries. One model per source,
no business logic, nothing joined.

**marts** is where the shape changes: sources get combined, columns get derived, and the result is
organised around the questions people ask rather than around the systems the data came from.

Each layer has one job, so when something breaks it is clear which part to look at.
