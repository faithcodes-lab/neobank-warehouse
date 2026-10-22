# Architecture

Three diagrams. The first shows what runs and in what order. The second shows every table and
where it comes from. The third shows the card payment lifecycle, which is the thing that makes the
modelling awkward.

All are written in Mermaid, which GitHub renders in the browser.

## What actually runs

In a real bank, data appears because people do things. Someone taps a card, someone opens an
account, a shop claims its money. Backend services record each of those.

There are no real people here and no real services. One Python program stands in for the lot,
writing files that look like what those services would have sent.

```mermaid
flowchart TD
    subgraph world["What happens in a real bank"]
        w1["a customer signs up<br/>or changes their address"]
        w2["someone opens or closes<br/>a current or savings account"]
        w3["a customer taps their card<br/>at a till"]
        w4["a shop claims the money<br/>it is owed, in a daily batch"]
        w5["a shop gets paid by a customer<br/>for the first time"]
    end

    gen["generator<br/>one Python program<br/>pretends all of the above happened"]

    subgraph out["what it writes, NDJSON files on disk"]
        f1["customers<br/>one file per day"]
        f2["accounts<br/>one file per day"]
        f3["card authorisations<br/>one file per day"]
        f4["payments<br/>one file per day"]
        f5["merchants<br/>one file, no date"]
    end

    load["bq load<br/>sends each file to BigQuery"]
    rawt[("BigQuery raw<br/>one table per file")]
    dbtrun["dbt run<br/>builds staging then marts"]
    final[("BigQuery marts<br/>the tables you query")]

    w1 & w2 & w3 & w4 & w5 --> gen
    gen --> f1 & f2 & f3 & f4 & f5
    f1 & f2 & f3 & f4 & f5 --> load
    load --> rawt
    rawt --> dbtrun
    dbtrun --> final
```

The top row is what the generator is imitating. Each real world action becomes one kind of file:

| What happens | Becomes |
|---|---|
| a customer signs up or moves house | the customer file |
| someone opens or closes an account | the account file |
| a customer taps their card | the card authorisations file |
| a shop claims its money | the payments file |
| a shop is paid for the first time | a new row in the merchant file |

Three things you run, in order:

1. `python generator/...` writes the files
2. `bq load` puts them in BigQuery
3. `dbt run` builds everything on top

Only step 1 exists so far, and only the merchants part of it.

## Every table and where it comes from

Same pipeline, now showing each table rather than each step.

```mermaid
flowchart TD
    gen["generator"]

    subgraph raw["BigQuery raw<br/>exactly what arrived, never edited"]
        r1[("raw_customers")]
        r2[("raw_accounts")]
        r3[("raw_card_authorisations")]
        r4[("raw_payments")]
        r5[("raw_merchants")]
    end

    subgraph staging["dbt staging<br/>views, renamed and typed, duplicates removed"]
        s1["stg_customers"]
        s2["stg_accounts"]
        s3["stg_card_authorisations"]
        s4["stg_payments"]
        s5["stg_merchants"]
    end

    subgraph marts["dbt marts<br/>tables, the ones people query"]
        d1["dim_customer<br/>SCD2"]
        d2["dim_account<br/>SCD2"]
        d3["dim_merchant"]
        d4["dim_date<br/>generated, no source"]
        ft1["fct_card_authorisations"]
        ft2["fct_transactions"]
        ft3["fct_account_daily_balance"]
    end

    gen --> r1 & r2 & r3 & r4 & r5

    r1 --> s1
    r2 --> s2
    r3 --> s3
    r4 --> s4
    r5 --> s5

    s1 --> d1
    s2 --> d2
    s5 --> d3
    s3 --> ft1
    s3 --> ft2
    s4 --> ft2
    s2 --> ft3
    s4 --> ft3
```

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
