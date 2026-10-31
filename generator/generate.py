"""Generates all source data for the warehouse as NDJSON files.

Stands in for the bank's backend services, which this project does not have.
Produces the five sources of data that the warehouse needs:

    merchants              reference data, one undated file
    customers              daily snapshot, one file per day
    accounts               daily snapshot, one file per day
    card authorisations    events, one file per ingestion date
    payments               settlement events, one file per ingestion date

The random seed is fixed, so every run produces the same data.

Run with:
    python generator/generate.py
"""

import json  # turns python data into JSON text
import os  # works with the operating system, like creating files and folders.
import uuid  # generates unique IDs
import random  # generates random numbers, used for creating random data.
import datetime  # works with dates and times.
import shutil  # for deleting the data folder before generating new data

# set the random seed for reproducibility
random.seed(42)

# facts about the data that will be generated
# The bank size and timeline
START_DATE = datetime.date(2026, 7, 1)  # first day of the data to generate
NUMBER_OF_DAYS = 92  # number of days to generate the data for
STARTING_CUSTOMERS = 200  # number of customers to start with
# probability that a customer has a savings account
SAVINGS_ACCOUNT_PROBABILITY = 0.3

# How the customers change over time: new signups, country moves, and closures.
MAX_DAILY_SIGNUPS = 3  # each day, between 0 and 3 new customers join the bank.
COUNTRY_MOVE_CHANCE = 0.001  # chance a customer moves country on any given day
CLOSURE_CHANCE = 0.0005      # chance a customer leaves the bank on any given day
CURRENCY_BY_COUNTRY = {    # maps country codes to currency codes
    "GB": "GBP",
    "US": "USD",
    "DE": "EUR",
    "FR": "EUR",
    "ES": "EUR"
}

UTC_OFFSET_HOURS_BY_COUNTRY = {
    "GB": 1, # British Summer Time (BST) is UTC+1
    "US": -4, # Eastern Daylight Time (EDT) is UTC-4
    "DE": 2, # Central European Summer Time (CEST) is UTC+2
    "FR": 2, # Central European Summer Time (CEST) is UTC+2
    "ES": 2, # Central European Summer Time (CEST) is UTC+2
}

# How card taps behave
MAX_DAILY_TAPS = 3          # each open current account makes 0 to 3 card taps a day
DECLINE_CHANCE = 0.05       # 1 in 20 taps is declined
LATE_ARRIVAL_CHANCE = 0.02  # 1 in 50 taps reaches the warehouse hours late
DECLINE_REASONS = ["insufficient_funds",
                   "suspected_fraud", "card_expired", "incorrect_pin"]
DUPLICATE_CHANCE = 0.01  # 1 in 100 taps is delivered twice
# smallest and largest tap per category, in minor units (pence or cents)
AMOUNT_RANGE_BY_CATEGORY = {
    "Groceries": (300, 12000),
    "Eating Out": (400, 6000),
    "Petrol": (2000, 9000),
    "Pharmacy": (200, 3000),
    "Transport": (250, 15000),
    "General Retail": (1000, 50000),
    "Health & Beauty": (300, 4000),
    "Shopping": (500, 30000),
}

# How payments behave
# 3 in 100 approved taps are never claimed by the merchant
NEVER_SETTLES_CHANCE = 0.03
REFUND_CHANCE = 0.02         # 2 in 100 captures are later refunded
# restaurants and cafes: can settle up to 20% higher, for tips
TIP_MCCS = ["5812", "5814"]
# petrol stations: settle for what was actually pumped, often less
FUEL_MCCS = ["5541"]


# Merchants are the businesses that customers spend money with.
# Each merchant has a name, a category, and a Merchant Category Code (MCC).
# The MCC is a four-digit number used to classify merchants by the type of goods or services they provide.

MERCHANTS = [
    # United Kingdom
    {"merchant_name": "Tesco", "category": "Groceries",
        "mcc": "5411", "country": "GB"},
    {"merchant_name": "Pret", "category": "Eating Out",
        "mcc": "5812", "country": "GB"},
    {"merchant_name": "Shell", "category": "Petrol", "mcc": "5541", "country": "GB"},
    {"merchant_name": "Lloyds Pharmacy",
        "category": "Pharmacy", "mcc": "5912", "country": "GB"},
    {"merchant_name": "National Express",
        "category": "Transport", "mcc": "4111", "country": "GB"},
    {"merchant_name": "JD Sports", "category": "General Retail",
        "mcc": "5999", "country": "GB"},
    {"merchant_name": "Boots", "category": "Health & Beauty",
        "mcc": "5912", "country": "GB"},
    {"merchant_name": "Argos", "category": "Shopping",
        "mcc": "5999", "country": "GB"},
    {"merchant_name": "Sainsburys", "category": "Groceries",
        "mcc": "5411", "country": "GB"},
    {"merchant_name": "Aldi", "category": "Groceries",
        "mcc": "5411", "country": "GB"},
    {"merchant_name": "Nandos", "category": "Eating Out",
        "mcc": "5812", "country": "GB"},
    {"merchant_name": "Greggs", "category": "Eating Out",
        "mcc": "5814", "country": "GB"},
    {"merchant_name": "BP", "category": "Petrol", "mcc": "5541", "country": "GB"},
    {"merchant_name": "Trainline", "category": "Transport",
        "mcc": "4112", "country": "GB"},
    {"merchant_name": "Superdrug", "category": "Health & Beauty",
        "mcc": "5912", "country": "GB"},
    {"merchant_name": "Currys", "category": "General Retail",
        "mcc": "5732", "country": "GB"},
    # United States
    {"merchant_name": "Whole Foods Market",
        "category": "Groceries", "mcc": "5411", "country": "US"},
    {"merchant_name": "Chipotle", "category": "Eating Out",
        "mcc": "5812", "country": "US"},
    {"merchant_name": "Starbucks", "category": "Eating Out",
        "mcc": "5814", "country": "US"},
    {"merchant_name": "ExxonMobil", "category": "Petrol",
        "mcc": "5541", "country": "US"},
    {"merchant_name": "CVS Pharmacy", "category": "Pharmacy",
        "mcc": "5912", "country": "US"},
    {"merchant_name": "Amtrak", "category": "Transport",
        "mcc": "4112", "country": "US"},
    {"merchant_name": "Best Buy", "category": "General Retail",
        "mcc": "5732", "country": "US"},
    {"merchant_name": "Ulta Beauty", "category": "Health & Beauty",
        "mcc": "5977", "country": "US"},
    {"merchant_name": "Target", "category": "Shopping",
        "mcc": "5310", "country": "US"},
    # Germany
    {"merchant_name": "REWE", "category": "Groceries",
        "mcc": "5411", "country": "DE"},
    {"merchant_name": "Lidl", "category": "Groceries",
        "mcc": "5411", "country": "DE"},
    {"merchant_name": "Vapiano", "category": "Eating Out",
        "mcc": "5812", "country": "DE"},
    {"merchant_name": "Aral", "category": "Petrol", "mcc": "5541", "country": "DE"},
    {"merchant_name": "DocMorris", "category": "Pharmacy",
        "mcc": "5912", "country": "DE"},
    {"merchant_name": "Deutsche Bahn", "category": "Transport",
        "mcc": "4112", "country": "DE"},
    {"merchant_name": "MediaMarkt", "category": "General Retail",
        "mcc": "5732", "country": "DE"},
    {"merchant_name": "Douglas", "category": "Health & Beauty",
        "mcc": "5977", "country": "DE"},
    # France
    {"merchant_name": "Carrefour", "category": "Groceries",
        "mcc": "5411", "country": "FR"},
    {"merchant_name": "Paul", "category": "Eating Out",
        "mcc": "5814", "country": "FR"},
    {"merchant_name": "Flunch", "category": "Eating Out",
        "mcc": "5812", "country": "FR"},
    {"merchant_name": "TotalEnergies", "category": "Petrol",
        "mcc": "5541", "country": "FR"},
    {"merchant_name": "Pharmacie Lafayette",
        "category": "Pharmacy", "mcc": "5912", "country": "FR"},
    {"merchant_name": "SNCF", "category": "Transport",
        "mcc": "4112", "country": "FR"},
    {"merchant_name": "Fnac", "category": "General Retail",
        "mcc": "5732", "country": "FR"},
    {"merchant_name": "Sephora", "category": "Health & Beauty",
        "mcc": "5977", "country": "FR"},
    {"merchant_name": "Galeries Lafayette",
        "category": "Shopping", "mcc": "5311", "country": "FR"},
    # Spain
    {"merchant_name": "Mercadona", "category": "Groceries",
        "mcc": "5411", "country": "ES"},
    {"merchant_name": "100 Montaditos", "category": "Eating Out",
        "mcc": "5812", "country": "ES"},
    {"merchant_name": "Telepizza", "category": "Eating Out",
        "mcc": "5814", "country": "ES"},
    {"merchant_name": "Repsol", "category": "Petrol", "mcc": "5541", "country": "ES"},
    {"merchant_name": "Renfe", "category": "Transport",
        "mcc": "4112", "country": "ES"},
    {"merchant_name": "Worten", "category": "General Retail",
        "mcc": "5732", "country": "ES"},
    {"merchant_name": "Druni", "category": "Health & Beauty",
        "mcc": "5977", "country": "ES"},
    {"merchant_name": "El Corte Ingles",
        "category": "Shopping", "mcc": "5311", "country": "ES"}
]


def build_merchants() -> list[dict]:
    """Gives each merchant a four-digit unique ID and returns them as records."""
    records = []

    for position, merchant in enumerate(MERCHANTS, start=1):
        record = {
            "merchant_id": f"mer_{position:04d}",
            "merchant_name": merchant["merchant_name"],
            "category": merchant["category"],
            "mcc": merchant["mcc"],
            "country": merchant["country"],
        }
        records.append(record)

    return records

# customers are the people who use the bank's services.
# Each customer has a unique ID, a name, a country, a date of birth, and a signup date.
# Some customers may have closed their accounts, in which case they will also have a closed date.


FIRST_NAMES = [
    "Alice", "Bob", "Charlie", "David", "Eva", "Frank", "Grace", "Hannah",
    "Ian", "Jack", "Kathy", "Liam", "Mia", "Noah", "Olivia", "Paul",
    "Quinn", "Rachel", "Sam", "Tina", "Uma", "Victor", "Wendy",
    "Xander", "Yara", "Zane", "James", "Sofia", "Chloe", "Daniel"
]

LAST_NAMES = [
    "Walsh", "Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis",
    "Garcia", "Rodriguez", "Wilson", "Martinez", "Anderson", "Taylor",
    "Thomas", "Hernandez", "Moore", "Martin", "Jackson", "Thompson",
    "White", "Lopez", "Lee", "Gonzalez", "Harris", "Clark", "Lewis",
    "Robinson", "Walker", "Perez", "Hall", "Young", "Allen"
]

# randomly generates a customer name by picking a first and last name from the lists above.


def generate_customer_name() -> str:
    """Generates a random customer name."""
    return random.choice(FIRST_NAMES) + " " + random.choice(LAST_NAMES)

# random date helper function to generate a date of birth for a customer and signup dates.


def random_date(start: datetime.date, end: datetime.date) -> datetime.date:
    """Returns a random date between start and end."""
    days = (end - start).days
    return start + datetime.timedelta(days=random.randint(0, days))


def build_customer(number: int, signup_date: datetime.date) -> dict:
    """Makes one customer with a random name, country and birthday."""
    return {
        "customer_id": f"cus_{number:04d}",           # number 7 "cus_0007"
        "full_name": generate_customer_name(),
        "country": random.choice(list(CURRENCY_BY_COUNTRY.keys())),
        "date_of_birth": random_date(datetime.date(1950, 1, 1), datetime.date(2002, 1, 1)).isoformat(),
        "signup_date": signup_date.isoformat(),
        "closed_date": None,
    }


def build_starting_customers() -> list[dict]:
    """Build the initial set of customers."""
    customer_records = []

    for numbers in range(1, STARTING_CUSTOMERS + 1):
        signup_date = random_date(datetime.date(
            2020, 1, 1), START_DATE - datetime.timedelta(days=1))
        customer_records.append(build_customer(numbers, signup_date))

    return customer_records


# Accounts are the bank accounts that customers have.

def build_account(number: int, customer: dict, account_type: str, opened_date: datetime.date) -> dict:
    """Makes one open account for a customer."""
    return {
        "account_id": f"acc_{number:04d}",
        "customer_id": customer["customer_id"],
        "account_type": account_type,                     # "current" or "savings"
        "currency": CURRENCY_BY_COUNTRY[customer["country"]],
        "opened_date": opened_date.isoformat(),
        "closed_date": None,
        "status": "open",
    }


def build_starting_accounts(customer_records: list[dict]) -> list[dict]:
    """Gives every customer a current account and some customers a savings account."""
    account_records = []

    for customer in customer_records:
        signup_date = datetime.date.fromisoformat(customer["signup_date"])

        account_records.append(build_account(
            len(account_records) + 1, customer, "current", signup_date))

        if random.random() < SAVINGS_ACCOUNT_PROBABILITY:
            savings_opened_date = random_date(
                signup_date, START_DATE - datetime.timedelta(days=1))
            account_records.append(build_account(
                len(account_records) + 1, customer, "savings", savings_opened_date))

    return account_records


def close_customer(customer: dict, account_records: list[dict], closure_date: datetime.date) -> None:
    """Marks a customer as closed, and closes all of their open accounts the same day."""
    customer["closed_date"] = closure_date.isoformat()

    for account in account_records:
        if account["customer_id"] == customer["customer_id"] and account["status"] == "open":
            account["status"] = "closed"
            account["closed_date"] = closure_date.isoformat()


def apply_daily_changes(customer_records: list[dict], account_records: list[dict], change_date: datetime.date) -> None:
    """Applies one day's signups, country moves and closures to the customers and accounts."""

    # new signups: each gets a current account opened the same day
    for _ in range(random.randint(0, MAX_DAILY_SIGNUPS)):
        customer = build_customer(len(customer_records) + 1, change_date)
        customer_records.append(customer)
        account_records.append(build_account(
            len(account_records) + 1, customer, "current", change_date))

    # existing customers: some move country, a few leave
    for customer in customer_records:
        if customer["closed_date"] is not None:
            continue   # already left the bank, so nothing more happens to them

        if random.random() < COUNTRY_MOVE_CHANCE:
            other_countries = [
                c for c in CURRENCY_BY_COUNTRY if c != customer["country"]]
            customer["country"] = random.choice(other_countries)

        elif random.random() < CLOSURE_CHANCE:
            close_customer(customer, account_records, change_date)

def local_timezone(country: str) -> datetime.timezone:
    """Returns the summer time zone for a country, as an offset from UTC."""
    return datetime.timezone(datetime.timedelta(hours=UTC_OFFSET_HOURS_BY_COUNTRY[country]))


def to_utc_text(moment: datetime.datetime) -> str:
    """Converts a moment to UTC and writes it with a Z, like 2026-07-01T08:00:00Z."""
    return moment.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# daily snapshots of customers and accounts.

def add_snapshot_fields(records: list[dict], snapshot_date: datetime.date) -> list[dict]:
    """Returns a copy of each record with snapshot_date and extracted_at added."""
    extracted_at = datetime.datetime.combine(
        # the next day, when the snapshot is extracted
        snapshot_date + datetime.timedelta(days=1),
        datetime.time(2, 0),  # at 2am
        tzinfo=datetime.timezone.utc # the bank's own clock
    )
    snapshot = []
    for record in records:
        snapshot.append({
            "snapshot_date": snapshot_date.isoformat(),
            "extracted_at": to_utc_text(extracted_at),
            **record,
        })
    return snapshot


def random_time_on(day: datetime.date, timezone: datetime.timezone) -> datetime.datetime:
    """Returns a random moment during the given day, in the specified timezone."""
    midnight = datetime.datetime.combine(day, datetime.time(0, 0), tzinfo=timezone)
    return midnight + datetime.timedelta(seconds=random.randint(0, 24 * 60 * 60 - 1))


def build_authorisation(account: dict, merchant: dict, auth_day: datetime.date) -> dict:
    """Makes one card tap on an account at a merchant."""
    created_ts = random_time_on(auth_day, local_timezone(merchant["country"]))

    # most taps reach the warehouse within half an hour, a few arrive hours later
    delay = datetime.timedelta(minutes=random.randint(1, 30))
    if random.random() < LATE_ARRIVAL_CHANCE:
        delay = delay + datetime.timedelta(hours=random.randint(1, 24))
    ingested_ts = created_ts + delay

    # an amount that suits what the merchant sells
    smallest, largest = AMOUNT_RANGE_BY_CATEGORY[merchant["category"]]

    if random.random() < DECLINE_CHANCE:
        outcome = "declined"
        decline_reason = random.choice(DECLINE_REASONS)
    else:
        outcome = "approved"
        decline_reason = None

    return {
        "event_id": str(uuid.UUID(int=random.getrandbits(128), version=4)),
        "account_id": account["account_id"],
        "merchant_id": merchant["merchant_id"],
        "mcc": merchant["mcc"],
        "amount_minor": random.randint(smallest, largest),
        "currency": account["currency"],
        "outcome": outcome,
        "decline_reason": decline_reason,
        "created_ts": created_ts.isoformat(), # the shop's local time, with its offset
        "ingested_ts": to_utc_text(ingested_ts), # the warehouse's clock, in UTC
    }


def redelivered(record: dict) -> dict:
    """Returns a copy of an event delivered again, 5 minutes to 6 hours after the original."""
    first_arrival = datetime.datetime.fromisoformat(record["ingested_ts"])
    delay = datetime.timedelta(minutes=random.randint(5, 6 * 60))

    copy = dict(record)
    copy["ingested_ts"] = to_utc_text(first_arrival + delay)
    return copy


def build_daily_authorisations(account_records: list[dict], merchant_records: list[dict], country_by_customer_id: dict, current_day: datetime.date) -> list[dict]:
    """Makes today's card taps for every open current account."""
    authorisations = []

    for account in account_records:
        if account["account_type"] != "current" or account["status"] != "open":
            continue  # savings accounts have no card, and closed accounts can't spend

        # customers only shop in the country they live in
        home_country = country_by_customer_id[account["customer_id"]]
        local_merchants = [m for m in merchant_records if m["country"] == home_country]

        for _ in range(random.randint(0, MAX_DAILY_TAPS)):
            merchant = random.choice(local_merchants)
            authorisation_record = build_authorisation(
                account, merchant, current_day)
            authorisations.append(authorisation_record)

            if random.random() < DUPLICATE_CHANCE:
                # the same event, delivered again later
                authorisations.append(redelivered(authorisation_record))

    return authorisations


def add_by_ingestion_date(grouped: dict, record: dict) -> None:
    """Files a record under the date it reached the warehouse."""
    record_ingestion_date = record["ingested_ts"][:10]
    if record_ingestion_date not in grouped:
        grouped[record_ingestion_date] = []
    grouped[record_ingestion_date].append(record)


# payments are the settlements: the merchant claiming the money a few days after the tap.
# Each one points back to its tap through authorisation_event_id. See ADR 2.

def settlement_time(day: datetime.date, timezone: datetime.timezone) -> datetime.datetime:
    """Merchants send their claims in a nightly batch, between 22:00 and 23:00 their time."""
    return datetime.datetime.combine(day, datetime.time(22, 0), tzinfo=timezone) + datetime.timedelta(minutes=random.randint(0, 59))

def build_payment(tap_authorisation: dict, settlement_type: str, amount_minor: int, created_ts: datetime.datetime) -> dict:
    """Makes one settlement event for a tap: a capture or a refund."""
    ingested_ts = created_ts + \
        datetime.timedelta(minutes=random.randint(1, 30))

    return {
        "event_id": str(uuid.UUID(int=random.getrandbits(128), version=4)),
        "authorisation_event_id": tap_authorisation["event_id"],
        "account_id": tap_authorisation["account_id"],
        "merchant_id": tap_authorisation["merchant_id"],
        "amount_minor": amount_minor,
        "currency": tap_authorisation["currency"],
        "settlement_type": settlement_type,
        "created_ts": created_ts.isoformat(),
        "ingested_ts": to_utc_text(ingested_ts),
    }


def build_settlements(tap_authorisation: dict) -> list[dict]:
    """Returns the payments for one approved tap: none, a capture, or a capture and a refund."""
    if random.random() < NEVER_SETTLES_CHANCE:
        return []  # the merchant never claims it, so it stays pending

    # the capture amount: usually what was authorised, with tips and fuel as exceptions
    amount = tap_authorisation["amount_minor"]
    if tap_authorisation["mcc"] in TIP_MCCS:
        amount = round(amount * random.uniform(1.0, 1.2))
    elif tap_authorisation["mcc"] in FUEL_MCCS:
        amount = round(amount * random.uniform(0.4, 1.0))

    # the merchant claims it in their batch 1 to 3 days after the tap
    tap_moment = datetime.datetime.fromisoformat(tap_authorisation["created_ts"])
    capture_time = settlement_time(
        tap_moment.date() + datetime.timedelta(days=random.randint(1, 3)), tap_moment.tzinfo)
    payments = [build_payment(
        tap_authorisation, "capture", amount, capture_time)]

    # occasionally the money is given back a few days later
    if random.random() < REFUND_CHANCE:
        refund_time = settlement_time(
            capture_time.date() + datetime.timedelta(days=random.randint(1, 10)), tap_moment.tzinfo)
        payments.append(build_payment(tap_authorisation,
                        "refund", amount, refund_time))

    return payments


# write the records to NDJSON files

def write_ndjson(records: list[dict], filename: str) -> None:
    """Writes one JSON object per line, creating the folder if needed."""
    folder = os.path.dirname(filename)
    if folder:
        os.makedirs(folder, exist_ok=True)

    with open(filename, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")

    print("wrote", len(records), "records to", filename)


# runs the data generation functions and writes the output to NDJSON files.
if __name__ == "__main__":

    # start from an empty data folder, so no file from an earlier run is left behind
    shutil.rmtree("data", ignore_errors=True)

    merchants = build_merchants()  # kept in a variable, the card taps need it
    write_ndjson(merchants, "data/merchants.ndjson")

    customers = build_starting_customers()
    accounts = build_starting_accounts(customers)

    # filled during the loop, written at the end
    authorisations_by_ingestion_date = {}
    payments_by_ingestion_date = {}
    # taps already settled, so a duplicate delivery isn't settled twice
    settled_event_ids = set()

    for day_number in range(NUMBER_OF_DAYS):
        today = START_DATE + datetime.timedelta(days=day_number)
        apply_daily_changes(customers, accounts, today)

        write_ndjson(
            # stamp today's dates on every customer
            add_snapshot_fields(customers, today),
            # e.g. data/customers/2026-07-01.ndjson
            f"data/customers/{today.isoformat()}.ndjson",
        )

        write_ndjson(
            add_snapshot_fields(accounts, today),          # same for accounts
            # e.g. data/accounts/2026-07-01.ndjson
            f"data/accounts/{today.isoformat()}.ndjson",
        )

        # where each customer lives today, so their card taps are at local shops
        country_by_customer_id = {c["customer_id"]: c["country"] for c in customers}
        for authorisation in build_daily_authorisations(accounts, merchants, country_by_customer_id, today):
            add_by_ingestion_date(
                authorisations_by_ingestion_date, authorisation)

            # settle each approved tap once, even if it was delivered twice
            if authorisation["outcome"] == "approved" and authorisation["event_id"] not in settled_event_ids:
                settled_event_ids.add(authorisation["event_id"])
                for payment in build_settlements(authorisation):
                    add_by_ingestion_date(payments_by_ingestion_date, payment)

                    if random.random() < DUPLICATE_CHANCE:
                        # the same settlement event, delivered again later
                        add_by_ingestion_date(payments_by_ingestion_date, redelivered(payment))

    # after all 92 days, write one file per ingestion date
    for ingestion_date, day_authorisations in sorted(authorisations_by_ingestion_date.items()):
        write_ndjson(day_authorisations,
                     f"data/card_authorisations/{ingestion_date}.ndjson")

    for ingestion_date, day_payments in sorted(payments_by_ingestion_date.items()):
        write_ndjson(day_payments, f"data/payments/{ingestion_date}.ndjson")
