# Architecture

Two views of the same system. The flow diagram shows where data goes. The sequence diagram shows
the card payment lifecycle that makes the modelling awkward.

Both are written in Mermaid, which GitHub renders directly in the browser.

## Data flow

```mermaid
flowchart TD
    subgraph sources["Simulated backend services"]
        cust["customer service<br/>daily snapshot"]
        acct["account service<br/>daily snapshot"]
        card["card service<br/>authorisation events"]
        pay["payment service<br/>settlement events"]
        mer["merchant reference<br/>lookup, rarely changes"]
    end

    subgraph files["NDJSON files on disk"]
        f1["data/customers/2026-03-01.ndjson"]
        f2["data/accounts/2026-03-01.ndjson"]
        f3["data/card_authorisations/2026-03-01.ndjson"]
        f4["data/payments/2026-03-01.ndjson"]
        f5["data/merchants.ndjson"]
    end

    subgraph raw["BigQuery raw<br/>append only, partitioned by ingestion date"]
        r1[("raw_customers")]
        r2[("raw_accounts")]
        r3[("raw_card_authorisations")]
        r4[("raw_payments")]
        r5[("raw_merchants")]
    end

    subgraph staging["dbt staging<br/>views, renamed and typed, duplicates resolved"]
        s1["stg_customers"]
        s2["stg_accounts"]
        s3["stg_card_authorisations"]
        s4["stg_payments"]
        s5["stg_merchants"]
    end

    subgraph marts["dbt marts<br/>tables, the star schema"]
        d1["dim_customer<br/>SCD2"]
        d2["dim_account<br/>SCD2"]
        d3["dim_merchant"]
        d4["dim_date"]
        ft1["fct_card_authorisations"]
        ft2["fct_transactions"]
        ft3["fct_account_daily_balance"]
    end

    subgraph consumers["Who reads it"]
        c1["Internal reporting"]
        c2["Financial and regulatory returns"]
    end

    cust --> f1 --> r1 --> s1
    acct --> f2 --> r2 --> s2
    card --> f3 --> r3 --> s3
    pay --> f4 --> r4 --> s4
    mer --> f5 --> r5 --> s5

    s1 --> d1
    s2 --> d2
    s5 --> d3
    s3 --> ft1
    s3 --> ft2
    s4 --> ft2
    s2 --> ft3
    s4 --> ft3

    d1 --> c1
    d2 --> c1
    d3 --> c1
    d4 --> c1
    ft1 --> c1
    ft2 --> c1
    ft2 --> c2
    ft3 --> c2
```

Things worth noticing in that diagram.

**Raw is never read by anything except staging.** If a transformation turns out to be wrong, the
warehouse is rebuilt from raw without going back to the source systems.

**`fct_transactions` has two inputs.** It needs both the authorisation and the settlement, because
transaction status is derived from whether a settlement arrived. No source sends that column.

**`dim_date` has no input.** It is generated from a date range rather than loaded from anywhere,
since nothing upstream emits a calendar.

## Card payment lifecycle

This is the sequence that makes the modelling interesting. One card tap produces two events, days
apart, possibly with different amounts.

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
    T->>N: authorisation request
    N->>B: authorisation request
    B->>B: check balance, fraud rules, limits
    B-->>N: approved
    N-->>T: approved
    T-->>C: receipt printed
    B->>B: hold 45.20 against available balance
    B->>W: authorisation event, created_ts 09:14

    Note over C,B: No money has moved. 45.20 is reserved, not taken.

    Note over C,W: Day 3, 22:00. Settlement.

    T->>N: merchant submits the day's batch
    N->>B: settlement, 45.20, capture
    B->>B: release the hold, move the money
    B->>W: settlement event, created_ts day 3

    Note over W: ingested_ts is later again, so a day 1 report<br/>run on day 2 was short by this transaction.

    W->>W: join authorisation to settlement, derive status
```

### Why this shape causes problems

**Authorisation is not spend.** The hold can be released without any money moving, if the merchant
abandons the authorisation or it expires. Reporting spend from authorisations overstates it.

**Settlement can differ from authorisation.** A restaurant authorises 40.00 and settles 48.00 once
a tip is added. A pay at pump petrol station authorises 100.00 and settles 62.00. The card networks
allow settlement above the authorised amount within a tolerance of roughly twenty percent, so a
test asserting that settlement never exceeds authorisation would fail on every tipped meal.

**Status is derived, not sent.** Nothing upstream knows whether a transaction is pending or
settled, because that depends on whether a second event has turned up yet.

| Authorisation | Settlement | Status |
|---|---|---|
| exists | none yet | pending |
| exists | capture | settled |
| exists | capture then refund | reversed |

**Two timestamps are needed.** `created_ts` says when it happened, `ingested_ts` says when the
warehouse received it. A transaction at 23:50 on 31 March arriving at 00:30 on 2 April belongs in
March by the first and April by the second. Both answers are correct, for different questions, and
reproducing what a past report said needs both.

## Layer responsibilities

```mermaid
flowchart LR
    raw["raw<br/><br/>exactly what arrived<br/>append only<br/>never edited<br/>the rebuild point"]
    stg["staging<br/><br/>rename and type<br/>flatten payloads<br/>resolve duplicates<br/>no business logic"]
    mart["marts<br/><br/>dimensional model<br/>derived columns<br/>business meaning<br/>what gets queried"]

    raw --> stg --> mart
```

Each layer has one job. Keeping them separate means source specific awkwardness is handled in
exactly one place, and everything downstream can assume clean, consistently named input.
