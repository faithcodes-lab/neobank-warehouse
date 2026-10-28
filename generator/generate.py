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
SAVINGS_ACCOUNT_PROBABILITY = 0.3  # probability that a customer has a savings account

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
    "White", "Lopez", "Lee", "Gonzalez", "Harris", "Clark", "Lewis", "Robinson", "Walker", "Perez", "Hall", "Young", "Allen"
]

# randomly generates a customer name by picking a first and last name from the lists above.


def generate_customer_name()-> str:
    """Generates a random customer name."""
    return random.choice(FIRST_NAMES) + " " + random.choice(LAST_NAMES)

# random date helper function to generate a date of birth for a customer and signup dates.


def random_date(start, end)-> datetime.date:
    """Returns a random date between start and end."""
    days = (end - start).days
    return start + datetime.timedelta(days=random.randint(0, days))


def build_starting_customers()-> list[dict]:
    """Build the initial set of customers."""
    customers = []

    for numbers in range(1, STARTING_CUSTOMERS + 1):
        customer_id = f"cus_{numbers:04d}"
        name = generate_customer_name()
        country = random.choice(list(CURRENCY_BY_COUNTRY.keys()))
        date_of_birth = random_date(datetime.date(1950, 1, 1), datetime.date(2002, 1, 1))
        signup_date = random_date(
            datetime.date(2020, 1, 1), START_DATE - datetime.timedelta(days=1))

        customer = {
            "customer_id": customer_id,
            "full_name": name,
            "country": country,
            "date_of_birth": date_of_birth.isoformat(),
            "signup_date": signup_date.isoformat(),
            "closed_date": None  # customers are active at the start
        }
        customers.append(customer)
    return customers


# Accounts are the bank accounts that customers have.
# Each account has a unique ID, a customer who owns it, a type (current or savings),
# a currency, an opened date, a closed date (if applicable), and a status (open or closed).

def build_starting_accounts(customers) -> list[dict]:
    """Gives every customer a current account and some customers a savings account, returning the accounts as records."""
    accounts = []
    next_account_number = 1 # used to generate unique account IDs

    for customer in customers:
        signup_date = datetime.date.fromisoformat(customer["signup_date"])
        currency = CURRENCY_BY_COUNTRY[customer["country"]]

        # every customer has a current account, opened when they sign up
        accounts.append({
            "account_id": f"acc_{next_account_number:04d}",
            "customer_id": customer["customer_id"],
            "account_type": "current",
            "currency": currency,
            "opened_date": signup_date.isoformat(),
            "closed_date": None,
            "status": "open"
        })
        next_account_number += 1

        # some customers also have a savings account, opened at a random date after signup
        if random.random() < SAVINGS_ACCOUNT_PROBABILITY:
            savings_opened_date = random_date(signup_date, START_DATE - datetime.timedelta(days=1))
            accounts.append({
                "account_id": f"acc_{next_account_number:04d}",
                "customer_id": customer["customer_id"],
                "account_type": "savings",
                "currency": currency,
                "opened_date": savings_opened_date.isoformat(),
                "closed_date": None,
                "status": "open"
            })
            next_account_number += 1
    return accounts




# write the records to NDJSON files

def write_ndjson(records, filename):
    """Writes one JSON object per line, creating the folder if needed."""
    folder = os.path.dirname(filename)
    if folder:
        os.makedirs(folder, exist_ok=True)

    with open(filename, "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")

    print("wrote", len(records), "records to", filename)


# runs the data generation functions and writes the output to NDJSON files.
if __name__ == "__main__":
    write_ndjson(build_merchants(), "data/merchants.ndjson")

    customers = build_starting_customers()
    write_ndjson(customers, "data/customers.ndjson")

    accounts = build_starting_accounts(customers)
    write_ndjson(accounts, "data/accounts.ndjson")
