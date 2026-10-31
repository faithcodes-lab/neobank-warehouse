# 3. Making the source data imperfect

Date: 2026-10-29

Status: accepted. Issues 1 to 6 are decided. They are not yet built into the generator.

## Context

The generator produces all five sources from ADR 1 and ADR 2, but the data is cleaner than real
service output.

Real bank data is messy. Systems resend messages, go down, change their format and record local
times. The warehouse's job is to turn that into numbers people can trust, and staging is the layer
that does the tidying. If the test data is clean, staging has nothing to do and there is no way to
show that it works. A bug that forgets to remove duplicates would go unnoticed, because the totals
would still look right.


## Decision

### Issue 1: redelivered events arrive later

#### What happens

Services use **at least once delivery**. When a service sends an event to the warehouse, it waits
for a reply saying the event arrived. If no reply comes, it cannot tell whether the event was lost
or only the reply was, so it sends the event again to be safe. Sending something twice is better
than losing a payment.

The result is a **duplicate**: the same event reaching the warehouse twice. The customer did
nothing twice and is only charged once. The duplicate exists only in the warehouse's copy of the
data.

A redelivery happens after a wait, so the copy arrives **later** than the original.

#### Real scenarios

**The lost reply.** Sarah taps her card once at Pret at 08:15 and walks off with her coffee. The
card service sends the authorisation to the warehouse, which saves it. The reply saying it arrived
is lost on the network. At 08:20 the card service, having heard nothing, sends the same
authorisation again.

**A restart part way through a batch.** At 23:50 the card service is sending a batch of events
when it crashes. After restarting at 01:10 it knows some of the batch got through but not which
events, so it sends the whole batch again. Some events now arrive twice, the copy on the next day.

**A busy day.** On Black Friday the systems are overloaded and replies are slow. Events whose
reply takes too long are treated as lost and sent again automatically.

**The merchant's batch.** Every evening Pret sends the bank its claims for the day. The payment
service passes Sarah's capture to the warehouse at 22:15, the reply is lost, and it sends the same
capture again at 23:40. Pret claimed once and Sarah paid once, but the warehouse has the capture
twice.

#### Telling a duplicate from two real purchases

Every real event gets its own `event_id` the moment it happens.

| Situation | `event_id`s | What it is |
|---|---|---|
| one tap, sent twice | the same, `abc-123` twice | one coffee, duplicated: keep one |
| two coffees bought | different, `abc-123` and `def-456` | two real purchases: keep both |

Two coffees bought seconds apart at the same price look identical in every other field, which is
why ADR 1 calls `event_id` the one field the project cannot work without.

#### What the generator does

For card authorisations **and** payments, 1 in 100 events is delivered twice. The copy keeps the
same `event_id` and `created_ts`, and gets a later `ingested_ts`: between 5 minutes and 6 hours
after the original arrived.

| | `event_id` | `created_ts` | `ingested_ts` | File |
|---|---|---|---|---|
| original | `abc-123` | 1 July 23:40 | 1 July 23:55 | `2026-07-01` |
| copy | `abc-123` | 1 July 23:40 | 2 July 01:10 | `2026-07-02` |

Most copies land on the same day as the original. Some cross midnight and land in the next day's
file, and so in a different partition.

A duplicated payment is only a copy of the same record. It does not create a second capture or
refund of its own.

#### What staging has to do

Keep **one row per `event_id`**, choosing the earliest `ingested_ts`. Because the copies can sit
in different partitions, deduplication has to look across days rather than within one.

This matters more for payments than for authorisations. Spend is reported from payments, so a
duplicated capture overstates it, and a duplicated refund gives the money back twice.

### Issue 2: optional fields are absent rather than null

#### What happens

When a field has no value, a service can send it in two ways:

```json
{"outcome": "approved", "decline_reason": null}
{"outcome": "approved"}
```

The first is **null**: the field is there, with no value. The second is **absent**: the field is
not there at all. Like a form, null is a blank box and absent is a form without the box.

Both usually mean the same thing, no value, but they look different, and the warehouse receives
both.

#### Real scenarios

**Saving space.** The card service sends millions of events a day. An approved authorisation never
has a decline reason, so sending `"decline_reason": null` millions of times is wasted space. The
developers set the service to skip empty fields. Many programming tools do this by default or with
one setting.

**Two teams, two habits.** The card team skips empty fields. The account team always sends every
field, with null when it is empty. Both are reasonable, and the warehouse receives data from both.

**An upgrade changes the habit.** The card service is upgraded in August and the new version skips
empty fields where the old one did not. The same source sends null before the upgrade and absent
after it, and nobody announces the change. This is tied to the schema change in issue 4.

#### What the generator does

Each service has its own habit:

| Service | Field | What it sends when empty |
|---|---|---|
| card service | `decline_reason`, on approved authorisations | null under v1, absent from v2 onwards |
| account service | `closed_date`, on open accounts | always absent |
| customer service | `closed_date`, on active customers | always null |

So the data shows a service that switches style, a service that always skips, and a service that
always sends. Payments have no optional fields, so nothing changes there.

#### When absent is a problem

A missing field is usually fine, but not always. Whether it is expected depends on the rest of the
record:

| Record | Field | Missing is |
|---|---|---|
| approved authorisation | `decline_reason` | expected: there is no reason to give |
| declined authorisation | `decline_reason` | a problem: it was declined, so the service should have sent a reason |
| open account | `closed_date` | expected: it is not closed |
| closed account | `closed_date` | a problem: it is closed, so it should have a date |

The field looks the same in both cases. Only the rest of the record tells them apart.

#### What staging has to do

Treat an absent field exactly like null, so that after staging every row has every column. Then
tests check that a missing value makes sense: a declined authorisation must have a decline reason,
and a closed account must have a closed date. A field the service failed to send is caught rather
than silently read as empty.

Two risks to avoid on the way in:

- **Code that expects the field.** Reading a field that is not there fails in most languages. In
  Python, `record["decline_reason"]` raises a `KeyError`.
- **BigQuery guessing the columns.** If a raw table's columns are guessed from the first file
  loaded, called schema auto detection, and that file never contains `closed_date`, the column is
  never created and later files that do contain it fail to load. Raw table columns have to be
  written down rather than guessed.

### Issue 3: timestamps carry local time zones

#### What happens

A clock reading on its own does not say when something happened, because 09:00 in London, Madrid
and New York are different moments. The reference clock everyone measures against is **UTC**
(Coordinated Universal Time). It belongs to no country and never changes for summer.

A timestamp in **local time with an offset** gives the time on the local clock plus how far that
clock is from UTC. A `+` offset is ahead of UTC and a `-` offset is behind it. `Z` means the time
is already UTC.

| Written as | Where | UTC |
|---|---|---|
| `2026-07-01T09:00:00+01:00` | London, summer | 08:00 |
| `2026-07-01T09:00:00+02:00` | Madrid | 07:00 |
| `2026-07-01T09:00:00-04:00` | New York, summer | 13:00 |
| `2026-07-01T08:00:00Z` | already UTC | 08:00 |

#### Real scenarios

**The wrong order.** Ana taps in Madrid at 00:30 on 2 July, local time. Tom taps in London at
23:45 on 1 July, local time. Sorted by clock reading, Tom comes first. In UTC Ana tapped at 22:30
and Tom at 22:45, so Ana came first.

**The wrong day.** Ana's tap says 2 July in Madrid, but it was still 1 July in London and in UTC.
If nobody decides which clock the bank reports by, one report puts it in July's first day and
another in the second, and the numbers do not match.

**The clocks change.** At the end of October the UK puts its clocks back an hour, so 01:30 happens
twice that night. Without an offset the two cannot be told apart. The simulated period is all
summer, so this only appears if the history is extended past October.

**Different systems, different clocks.** The terminal in the shop records the tap in its local
time. The warehouse records when the event arrived by its own clock, in UTC. One record carries
both.

#### What the generator does

Each merchant gets a `country`, and the merchant list grows to include shops in every country the
bank has customers in. New merchants are added at the end of the list, so existing merchant ids
do not change.

Customers only tap at merchants in their own country, so a tap is always in the account's
currency and no exchange rate is needed.

The exception is a customer who moves. They start shopping in their new country, but their accounts
keep the currency they were opened in, so someone who moves from the UK to France pays at Carrefour
from a GBP account. In real life the card network converts the amount. Here the tap is simply
recorded in the account's currency, and proper conversion belongs with spending abroad, a separate
issue for later. About 3 in 100 taps fall into this case.

| Timestamp | Recorded by | Format |
|---|---|---|
| `created_ts` on authorisations and payments | the service, at the merchant | local time with the merchant's offset |
| `ingested_ts` | the warehouse | UTC, ending in `Z` |
| `extracted_at` on snapshots | the bank's nightly job | UTC, ending in `Z` |

The summer offsets, which cover the whole simulated period:

| Country | Offset |
|---|---|
| GB | `+01:00`, British Summer Time |
| DE, FR, ES | `+02:00`, Central European Summer Time |
| US | `-04:00`, Eastern time |

The US spans four time zones. All US merchants are treated as being on New York time: Eastern time
covers the most people and is where US banking is centred. A real US operation would span all four.

#### What staging has to do

Convert every timestamp to UTC, so that times from different countries can be sorted and compared
on one clock. Where a report needs a local day, such as daily totals for the UK, it converts from
UTC once, on purpose, in one place.

### Issue 4: the card authorisation schema changes from v1 to v2

#### What happens

A **schema** is the agreed layout of a message: which fields it has, what each is called and what
kind of value it holds. The warehouse is built expecting that layout.

Services change their schema over time, for their own reasons, and the warehouse is usually not
asked first. Some changes are **backwards compatible**, such as adding a field, and old code keeps
working. Others are **breaking changes**, such as moving or renaming a field, and old code looks in
the old place and finds nothing.

#### Real scenarios

**A restructure for travel.** The card team plans for customers spending abroad, where a tap has
two amounts: what the shop charged and what left the account. To make room, they group the amount
and its currency together inside one `amount` field. The information is the same, only its place
has moved.

**A gradual rollout.** The card service runs on many servers. Upgrading them all at once is risky,
so it is done in stages. For a few days old and new layouts arrive mixed together, even for the
same customer on the same day.

**Nobody tells the warehouse.** The card team announces the upgrade in their own channel. If
staging only looks for `amount_minor`, new taps arrive with no amount. Either the load fails, or
worse, it succeeds with the amount empty, and spending reports quietly drop without any alarm.

#### What the generator does

From 15 August, card authorisations switch from v1 to v2. Two things change:

- v2 messages carry `"schema_version": 2`. v1 messages have no `schema_version` field at all,
  because a first version is rarely labelled.
- `amount_minor` and `currency` move inside a nested `amount` field, with `amount_minor` renamed
  `value_minor`.

Along with the upgrade, the card service stops sending an empty `decline_reason`, as described in
issue 2.

```json
v1:  {"event_id": "abc-123", "amount_minor": 4520, "currency": "GBP", "outcome": "approved", "decline_reason": null, ...}
v2:  {"event_id": "def-456", "schema_version": 2, "amount": {"value_minor": 4520, "currency": "GBP"}, "outcome": "approved", ...}
```

The rollout takes three days. Each tap is given v1 or v2 at random, with these chances:

| Day | v2 | v1 |
|---|---|---|
| up to 14 August | none | all |
| 15 August | 1 in 4 | 3 in 4 |
| 16 August | 1 in 2 | 1 in 2 |
| 17 August onwards | all | none |

Only card authorisations change. Payments, customers and accounts keep their layout.

#### What staging has to do

The raw table keeps every message as it arrived, and has to accept both layouts without rejecting
either.

Staging turns both into one shape, so that nothing downstream knows the change happened:

| Staging column | From v1 | From v2 |
|---|---|---|
| `schema_version` | 1, because the field is missing | `schema_version` |
| `amount_minor` | `amount_minor` | `amount.value_minor` |
| `currency` | `currency` | `amount.currency` |

Pulling a value out from inside `amount` is called **flattening**. Each message is read by its own
`schema_version`, not by its date, because during the rollout both layouts arrive on the same day.

Tests check that the amount and currency are never empty in either version, which catches a layout
staging does not handle, and that `schema_version` is only ever 1 or 2, which catches a surprise
v3.

### Issue 5: a transaction arrives before its account

#### What happens

Every card authorisation carries an `account_id`, a **foreign key** pointing at a record in the
account data. Usually the account is already in the warehouse. Sometimes a tap arrives for an
account the warehouse has not seen yet, because the account's details have not arrived. The tap is
real, the warehouse just learns about it in the wrong order.

Until its account arrives, the tap is an **orphan**: its foreign key points at nothing. The
standard name for the problem is a **late arriving dimension**, because the fact arrives before the
dimension row it belongs to.

#### Real scenarios

**Sign up and spend straight away.** A digital bank gives a customer a virtual card in the app as
soon as their identity checks pass, and they can add it to Apple Pay or Google Pay within minutes.
Jade opens her account at 10:00 on 3 August and buys lunch at 12:30. The tap arrives at 12:45, but
the account snapshot for 3 August is only taken at 02:00 on 4 August. For about 13 hours the
warehouse has Jade's lunch but no Jade. The generator already produces this for every new account
that taps on its first day.

**The account is missed from the extract.** Jade's account is approved and she can spend, but some
part of its setup is still finishing in the background, and the nightly job skips it. It first
appears in the 5 August snapshot, two days late. Her taps from the 3rd and 4th have no account to
join to.

**The extract fails that night.** On 21 August no account file is made at all (issue 6b), so an
account opened that day first appears on the 22nd.

**A real orphan.** Rarer: a tap points at an account that never appears, because of a bug, a test
account or a wrong id. That is a data error rather than lateness. It is not simulated here.

#### What the generator does

About 1 in 10 new accounts is left out of its first 1 or 2 account snapshots, chosen at random.
The customer still appears in the customer snapshot as normal, and the account can tap from its
first day. When the account does appear, its `opened_date` is the true day it opened, so the real
date is never lost. Every late account turns up eventually.

| File | `acc_0230` | Taps for `acc_0230` |
|---|---|---|
| 3 August snapshot | missing | 2 taps on 3 August |
| 4 August snapshot | missing | 1 tap on 4 August |
| 5 August snapshot | present, `opened_date: 2026-08-03` | taps continue |

#### What the warehouse has to do

Never drop a tap because its account is unknown. Joining taps to accounts and keeping only the
matches would quietly remove real spending from reports, with no error.

Instead, a tap whose account has not arrived is linked to a placeholder "unknown account" row in
`dim_account`, so its money is still counted. When the account arrives, the next run links the tap
to the real account.

A dbt `relationships` test checks that every tap's `account_id` exists in the account data. It is
set to warn rather than fail, because a short delay is expected. An orphan still unmatched after a
few days is a real problem.

### Issue 6: service downtime

**Downtime** is when a system stops working for a while: a crash, a failed update, a network
problem or planned maintenance. Every real system has some. Events and snapshots arrive in
different ways, so downtime hurts them differently, and the generator produces one of each.

#### 6a. The card event feed goes down

##### What happens

The system that sends card events to the warehouse stops, but the card service itself keeps
working. Customers carry on paying by card as usual, every payment is approved, and shops notice
nothing. The events wait in a **queue**, and when the feed is fixed they all arrive at once, in a
**burst**.

##### Real scenarios

**The feed breaks, the payments do not.** At 13:00 the feed crashes. Customers carry on paying by
card as usual, and every payment is approved. The events pile up in the queue. At 19:00 an
engineer fixes it and six hours of events arrive together.

**Nobody notices at first.** The dashboard shows almost no spending that afternoon, and someone in
finance asks whether nobody shopped. The data had not arrived yet. This is what **freshness
checks** are for: alarms that fire when no new data has arrived for too long. ADR 1 already says
that transactions going quiet for an hour is an incident.

**The whole card service goes down.** A worse outage, where the card service itself fails and taps
are declined or never reach it. That is a real drop in spending rather than a delay. It is not
simulated here.

##### What the generator does

On 8 September from 13:00 to 19:00 UTC, no card authorisations arrive. Taps still happen at their
normal times, so `created_ts` is unchanged. Every authorisation created during the outage gets an
`ingested_ts` between 19:00 and 20:00, after the feed recovers. Payments are not affected.

| Tap | `created_ts` | `ingested_ts` |
|---|---|---|
| a normal day | 14:10 | 14:25 |
| during the outage | 14:10 | 19:23 |

##### What the warehouse has to do

Freshness checks on card authorisations should fail during the outage, which gives the alarm a real
gap to be tested against. The burst has to load without anything being skipped or counted twice.
Reports run during the outage show too little spending and are correct once rerun after the burst,
and the gap between `created_ts` and `ingested_ts` shows what was delayed and by how much.

#### 6b. The nightly account extract fails

##### What happens

The account service's nightly job fails one night and nobody reruns it. That day's account
snapshot is **never made**.

It cannot be made later either. A snapshot is a picture of the accounts as they are at the moment
the job runs, and the account service does not keep a copy of how they were on earlier days. Once
the day has passed, its state is gone. That is why the file is missing for ever rather than late.

##### Real scenarios

**The job fails and nobody reruns it.** At 02:00 the job for 21 August starts, the server runs out
of disk space, and it fails. There is no alarm. The next night's job runs normally. There is never
a file for 21 August.

**A change on the missing day.** An account closes on 21 August. The 20 August file shows it open
and the 22 August file shows it closed. ADR 1 warned about this: miss a day and that day's changes
are invisible.

**The job is rerun late.** A softer version, where an engineer notices and reruns the job at 10:30.
The file exists, with a late `extracted_at`. Not simulated here, because nothing is lost.

##### What the generator does

No account snapshot is written for 21 August. The customer snapshot for that day is written as
normal, because only the account service failed.

| File | `acc_0055` |
|---|---|
| 20 August | `status: open` |
| 21 August | no file |
| 22 August | `status: closed`, `closed_date: 2026-08-21` |

##### What the warehouse has to do

The account history jumps from the 20th to the 22nd, so a change made on the 21st first appears on
the 22nd and is dated then. Where a record carries its own date, such as `closed_date`, the true
day can still be recovered. Where it does not, the true day is lost.

A lookup of an account as it was on 21 August falls back to the 20 August version, the last one
known. Card authorisations on the 21st are unaffected, because they come from a different service.

A test that expects an account snapshot for every day fails for 21 August, so the gap is known and
recorded rather than silently ignored.

## Consequences

Staging has real deduplication work to do, across partitions, for two sources.

Counting rows in a raw table no longer counts events. Anything that needs a count has to read from
staging, where duplicates are already removed.

Raw table schemas have to be declared, not auto detected, because a field can be missing from
every line of a file.

Some data quality tests depend on two fields together, such as outcome and decline reason, rather
than on one column being not null.

Every timestamp has to be converted to UTC before it is sorted, compared or grouped by day. A raw
timestamp column holds values in several offsets.

Merchant reference data gains a `country` field.

The raw card authorisation table has to hold two layouts at once, and staging has to read each
message by its `schema_version`. A third version would mean another change to staging.

Taps can point at accounts the warehouse has not received yet. Facts are joined to dimensions
without dropping unmatched rows, and `dim_account` needs a placeholder row for unknown accounts.

Freshness checks need a threshold per source. Card authorisations going quiet for an hour is an
incident. Merchant data being unchanged for a week is not.

Daily snapshots can have gaps that cannot be filled. History built from them has to treat a missing
day as unknown rather than as unchanged, and tests have to check that every day is present.


## Still open

- An `entry_mode` field on card authorisations (contactless, chip or online), left out of v2 for
  now. It could arrive in a later version, and fits with spending abroad.
- How the bank operates outside the UK: a licence per region, an EU subsidiary, a US partner bank
- Spending abroad. Customers only tap in their own country for now. Letting them tap abroad, as
  when travelling, means the merchant charges in its own currency and the account is debited in
  another, so it needs exchange rates. A separate issue for later.
- Whether raw tables store typed columns or one JSON payload column, decided with the load script
