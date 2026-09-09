{#
  dbt's default generate_schema_name macro prefixes a model's custom schema
  with the target schema (e.g. "analytics_staging"). Override it to use the
  custom schema literally, so `dbt run` produces plain `staging`/`analytics`
  schemas as documented in dbt/README.md.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
