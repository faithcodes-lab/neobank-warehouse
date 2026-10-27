"""Generates all source data for the warehouse as NDJSON files.

Stands in for the bank's backend services, which this project does not have.
Produces the five sources set out in ADR 1 and ADR 2:

    merchants              reference data, one undated file
    customers              daily snapshot, one file per day
    accounts               daily snapshot, one file per day
    card authorisations    events, one file per ingestion date
    payments               settlement events, one file per ingestion date

The random seed is fixed, so every run produces the same data.

Run with:
    python generator/generate.py
"""

import json # turns python data into JSON text
import os # works with the operating system, like creating files and folders.

import random # generates random numbers, used for creating random data. 
import uuid # generates unique identifiers.
from datetime import date, datetime, timedelta # works with dates and times.

# set the random seed for reproducibility
random.seed(42)

# facts about the data that will be generated

START_DATE = date(2026, 7, 1) # first day of the data to generate
NUMBER_OF_DAYS = 92 # number of days to generate the data for
STARTING_CUSTOMERS = 200 # number of customers to start with

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


def build_merchants():
    """Adds a padded id to each merchant and returns them as records."""
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


def write_ndjson(records, filename):
    """Writes one JSON object per line, creating the folder if needed."""
    folder = os.path.dirname(filename)
    if folder:
        os.makedirs(folder, exist_ok=True)

    with open(filename, "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")

    print("wrote", len(records), "records to", filename)


if __name__ == "__main__":
    write_ndjson(build_merchants(), "data/merchants.ndjson")
