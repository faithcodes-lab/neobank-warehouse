# Contributing

## Branching

Two long lived branches:

- `main` is production. It builds into the `analytics_*` datasets in BigQuery.
- `develop` is integration. It builds into the `dbt_dev_*` datasets.

Work happens on a short lived branch cut from `develop`, named after the change:
`feat/dim-account-scd2`, `fix/null-merchant-handling`. That branch is pull requested into
`develop`. When `develop` is in a releasable state it is pull requested into `main` and tagged.

Nothing is committed directly to `main` or `develop`. The separation means a development run
cannot overwrite the production datasets, because the dbt target decides the dataset name.

## Commits

Imperative, lower case, under 60 characters, no trailing full stop.

```
add scd2 snapshot for dim_account
fix null merchant handling in stg_transactions
bump dbt-bigquery to 1.12.1
```

Add a body only when the reason is not obvious from the diff.

## Pull requests

Title says what the change does. In the body, cover what it does, why, and how it was tested, in
a few sentences. Link the issue.

Worth writing about tradeoffs actually weighed. "Went with insert_overwrite because merge was
scanning the full table on every run" is useful. "Improved performance" is not.

## Setup

```bash
uv venv --python 3.12
uv pip install dbt-core dbt-bigquery
git config commit.template .gitmessage
git config core.hooksPath .githooks
```

Copy `profiles.yml.example` to `~/.dbt/profiles.yml` and set the project id. Then `dbt debug`.

## Checks

```bash
./scripts/check-style.sh staged   # runs on commit
./scripts/check-style.sh tree     # runs in CI
```

Documentation and ADRs are written in first person, and record what did not work as well as what
did. An ADR that ends "revisit this once volumes grow past a few million rows" is more useful
than one that pretends the decision is permanent.

## Definition of done

- Merged through a pull request
- CI green
- Every new model declares its grain, has a description, and has at least one test
- README or an ADR updated where the change warrants it
