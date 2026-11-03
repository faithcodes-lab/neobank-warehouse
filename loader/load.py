"""
Loads the generator's NDJSON files into the BigQuery raw tables.

Each line is stored whole in a JSON column called payload, alongside three columns the warehouse
adds: source_file, ingestion_date and loaded_at. Each file replaces its own day's partition, so
loading the same file twice changes nothing.

Load one file, or every file in data/:
    python loader/load.py data/payments/2026-07-02.ndjson
    python loader/load.py
"""

import datetime
import glob  # finds all the files matching a pattern, like data/payments/*.ndjson
import json
import os
import sys  # reads the file names typed after the command

from google.cloud import bigquery  # Google's library for working with BigQuery

# where the data comes from and goes to
PROJECT_ID = "neobank-warehouse"
DATASET = "raw"
DATA_FOLDER = "data"

# Every raw table has these four raw columns
RAW_SCHEMA = [
    # the line, as it arrives
    bigquery.SchemaField("payload", "JSON", mode="REQUIRED"),
    # the file it came from, e.g. payments/2026-07-02.ndjson
    bigquery.SchemaField("source_file", "STRING", mode="REQUIRED"),
    # the date it was ingested
    bigquery.SchemaField("ingestion_date", "DATE", mode="NULLABLE"),
    # the timestamp when it was loaded
    bigquery.SchemaField("loaded_at", "TIMESTAMP", mode="REQUIRED"),
]


def table_for(file_path: str) -> str:
    """Returns the raw table a file belongs in,
    like raw_payments for data/payments/2026-07-02.ndjson."""
    folder = os.path.basename(os.path.dirname(file_path))  # e.g. "payments"
    if folder == DATA_FOLDER:
        return "raw_merchants"  # merchants.ndjson is the only file directly in data/
    return "raw_" + folder


def ingestion_date_for(file_path: str) -> datetime.date | None:
    """Returns the date in a file's name, like 2 July 2026 for data/payments/2026-07-02.ndjson.
    Merchants have no date, so they get None."""
    if table_for(file_path) == "raw_merchants":
        return None
    file_name = os.path.basename(file_path)  # e.g. "2026-07-02.ndjson"
    return datetime.date.fromisoformat(file_name.removesuffix(".ndjson"))


def build_rows(file_path: str, loaded_at: str) -> list[dict]:
    """Reads one file and returns a row for each line: the line as payload, plus the three columns
    the warehouse adds."""
    source_file = os.path.relpath(
        file_path, DATA_FOLDER)  # e.g. "payments/2026-07-02.ndjson"
    day = ingestion_date_for(file_path)
    if day is None:
        ingestion_date = None  # merchants have no date
    else:
        ingestion_date = day.isoformat()  # e.g. "2026-07-02"

    rows = []
    with open(file_path, encoding="utf-8") as f:
        for line in f:
            rows.append({
                "payload": json.loads(line),
                "source_file": source_file,
                "ingestion_date": ingestion_date,
                "loaded_at": loaded_at,
            })
    return rows


def load_file(client: bigquery.Client, file_path: str, loaded_at: str) -> None:
    """Loads one file into its raw table, replacing that day's partition, or the whole table for
    merchants, so loading the same file twice changes nothing."""
    table = f"{PROJECT_ID}.{DATASET}.{table_for(file_path)}"  # neobank-warehouse.raw.raw_payments
    day = ingestion_date_for(file_path)

    job_config = bigquery.LoadJobConfig(
        schema=RAW_SCHEMA,
        # replace what is there instead of adding to it
        write_disposition="WRITE_TRUNCATE",
    )
    if day is None:
        destination = table  # merchants have no partitions, so the whole table is replaced
    else:
        # only this day's partition
        destination = f"{table}${day.strftime('%Y%m%d')}"
        job_config.time_partitioning = bigquery.TimePartitioning(
            field="ingestion_date")

    rows = build_rows(file_path, loaded_at)
    job = client.load_table_from_json(rows, destination, job_config=job_config)
    job.result()  # waits for BigQuery to finish, and stops with an error if the load failed
    print("loaded", len(rows), "rows from", file_path, "into", destination)


def all_files() -> list[str]:
    """Returns every file in data/: merchants first, then each source's daily files by date."""
    files = sorted(glob.glob(os.path.join(DATA_FOLDER, "*.ndjson")))  # merchants.ndjson
    files += sorted(glob.glob(os.path.join(DATA_FOLDER, "*", "*.ndjson")))  # every daily file
    return files


def main() -> None:
    """Loads the files named after the command, or every file in data/ if none are named."""
    client = bigquery.Client(project=PROJECT_ID, location="EU")
    # one time for the whole run, so every row loaded together has the same loaded_at
    loaded_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if len(sys.argv) > 1:
        files = sys.argv[1:]  # the files typed after the command
    else:
        files = all_files()  # nothing typed, so every file in data/

    for file_path in files:
        load_file(client, file_path, loaded_at)
    print("done:", len(files), "files loaded")


if __name__ == "__main__":
    main()
