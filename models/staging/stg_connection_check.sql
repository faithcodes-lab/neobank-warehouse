-- Throwaway model proving the chain works end to end: dbt compiles this,
-- sends it to BigQuery, and materialises the result as a view.
-- Delete once the first real staging model exists.
select
    'dbt reached bigquery' as status,
    current_date() as checked_on
