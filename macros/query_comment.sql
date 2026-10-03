{#
  Attaches the model name and target to every query dbt sends to BigQuery.
  Makes cost attributable per model in INFORMATION_SCHEMA.JOBS later on.
#}
{% macro query_comment(node) %}
  {%- set comment = {
    "app": "dbt",
    "target": target.name,
    "node_id": node.unique_id if node else "none"
  } -%}
  {{ tojson(comment) }}
{% endmacro %}
