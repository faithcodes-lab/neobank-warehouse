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

import random  # generates random numbers, used for creating random data.
import datetime  # works with dates and times.

# set the random seed for reproducibility
random.seed(42)

# facts about the data that will be generated

START_DATE = datetime.date(2026, 7, 1)  # first day of the data to generate
NUMBER_OF_DAYS = 92  # number of days to generate the data for
STARTING_CUSTOMERS = 200  # number of customers to start with
# probability that a customer has a savings account
SAVINGS_ACCOUNT_PROBABILITY = 0.3

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


# Merchants are the businesses that customers spend money with.
# Each merchant has a name, a category, and a Merchant Category Code (MCC).
# The MCC is a four-digit number used to classify merchants by the type of goods or services they provide.

MERCHANTS = [
    {"merchant_name": "Tesco", "category": "Groceries", "mcc": "5411"},
    {"merchant_name": "Pret", "category": "Eating Out", "mcc": "5812"},
    {"merchant_name": "Shell", "category": "Petrol", "mcc": "5541"},
    {"merchant_name": "Lloyds Pharmacy", "category": "Pharmacy", "mcc": "5912"},
    {"merchant_name": "National Express", "category": "Transport", "mcc": "4111"},
    {"merchant_name": "JD Sports", "category": "General Retail", "mcc": "5999"},
    {"merchant_name": "Boots", "category": "Health & Beauty", "mcc": "5912"},
    {"merchant_name": "Argos", "category": "Shopping", "mcc": "5999"},
    {"merchant_name": "Sainsburys", "category": "Groceries", "mcc": "5411"},
    {"merchant_name": "Aldi", "category": "Groceries", "mcc": "5411"},
    {"merchant_name": "Nandos", "category": "Eating Out", "mcc": "5812"},
    {"merchant_name": "Greggs", "category": "Eating Out", "mcc": "5814"},
    {"merchant_name": "BP", "category": "Petrol", "mcc": "5541"},
    {"merchant_name": "Trainline", "category": "Transport", "mcc": "4112"},
    {"merchant_name": "Superdrug", "category": "Health & Beauty", "mcc": "5912"},
    {"merchant_name": "Currys", "category": "General Retail", "mcc": "5732"},
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


def random_date(start, end) -> datetime.date:
    """Returns a random date between start and end."""
    days = (end - start).days
    return start + datetime.timedelta(days=random.randint(0, days))


def build_customer(number, signup_date) -> dict:
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
# Each account has a unique ID, a customer who owns it, a type (current or savings),
# a currency, an opened date, a closed date (if applicable), and a status (open or closed).

def build_account(number, customer, account_type, opened_date) -> dict:
    """Makes one open account for a customer."""
    return {
        "account_id": f"acc_{number:04d}",
        "customer_id": customer["customer_id"],
        "account_type": account_type,                         # "current" or "savings"
        "currency": CURRENCY_BY_COUNTRY[customer["country"]],
        "opened_date": opened_date.isoformat(),
        "closed_date": None,
        "status": "open",
    }


def build_starting_accounts(customer_records) -> list[dict]:
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

def close_customer(customer, accounts, today):
    """Marks a customer as closed, and closes all of their open accounts the same day."""
    customer["closed_date"] = today.isoformat()

    for account in accounts:
        if account["customer_id"] == customer["customer_id"] and account["status"] == "open":
            account["status"] = "closed"
            account["closed_date"] = today.isoformat() 

def apply_daily_changes(customer_records, account_records, change_date):
    """Applies one day's signups, country moves and closures to the customers and accounts."""

    # new signups: each gets a current account opened the same day
    for _ in range(random.randint(0, MAX_DAILY_SIGNUPS)):
        customer = build_customer(len(customer_records) + 1, change_date)
        customer_records.append(customer)
        account_records.append(build_account(len(account_records) + 1, customer, "current", change_date))

    # existing customers: some move country, a few leave
    for customer in customer_records:
        if customer["closed_date"] is not None:
            continue   # already left the bank, so nothing more happens to them

        if random.random() < COUNTRY_MOVE_CHANCE:
            other_countries = [c for c in CURRENCY_BY_COUNTRY if c != customer["country"]]
            customer["country"] = random.choice(other_countries)

        elif random.random() < CLOSURE_CHANCE:
            close_customer(customer, account_records, change_date)
            
# daily snapshots of customers and accounts.

def add_snapshot_fields(records, snapshot_date) -> list[dict]:
    """Returns a copy of each record with snapshot_date and extracted_at added."""
    extracted_at = datetime.datetime.combine(
        # the next day, when the snapshot is extracted
        snapshot_date + datetime.timedelta(days=1),
        datetime.time(2, 0)  # at 2am
    )
    snapshot = []
    for record in records:
        snapshot.append({
            "snapshot_date": snapshot_date.isoformat(),
            "extracted_at": extracted_at.isoformat(),
            **record,
        })
    return snapshot


# write the records to NDJSON files

def write_ndjson(records, filename):
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
    write_ndjson(build_merchants(), "data/merchants.ndjson")

    customers = build_starting_customers()

    accounts = build_starting_accounts(customers)
    for day_number in range(NUMBER_OF_DAYS):
        today = START_DATE + datetime.timedelta(days=day_number)
        apply_daily_changes(customers, accounts, today)  # signups, moves and closures for today

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
