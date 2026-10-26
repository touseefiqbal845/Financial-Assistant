# Operational dashboard queries

Execution rate: `sum(rate(finance_events_total{kind="execution"}[5m]))`

Failure rate: `sum(rate(finance_events_total{kind="execution",outcome="failed"}[5m]))`

P95 execution seconds: `histogram_quantile(0.95, sum by (le) (rate(finance_step_seconds_bucket{step="execution"}[5m])))`

Input tokens: `sum(increase(finance_model_tokens_total{direction="input"}[1h]))`

The API and worker are separate processes. Scrape the API metrics endpoint and the worker's authenticated internal port 9001 separately; an API-only scrape cannot observe worker metrics. No question, entity, user, or execution identifiers belong in metric labels.
