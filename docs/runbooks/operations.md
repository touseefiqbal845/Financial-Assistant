# Operations

## Deployment

Compose is local-only. Production requires HTTPS ingress, OIDC, managed secrets, application and source connection pools, resource/replica quotas, ingress rate limits, log retention, and an OTLP collector when tracing is enabled. Set `FIN_ENVIRONMENT=production`; development auth is rejected.

Run Alembic and checkpoint setup as a separate release job using migration credentials. Provision app, reader, and ingest roles with separate secrets. Runtime containers never need owner credentials. Validate source RLS and reader write denial after grants change.

Worker `/metrics` is available on internal port 9001 when `FIN_METRICS_TOKEN` is configured. API `/metrics` is authenticated separately using the same configured monitoring token. Scrape each process; do not assume metrics are shared across API and worker processes. Restrict monitoring ingress. Configure `OTEL_EXPORTER_OTLP_ENDPOINT` only to a trusted collector. Span attributes deliberately omit raw prompts and documents.

## Recovery and cancellation

After a crash, wait for the thirty-second lease to expire. Another worker claims and resumes the checkpointed graph. An in-flight model request may repeat and incur another charge. Cancellation is polled during execution; provider-side work may outlive client cancellation. All business tools are read-only.

Inspect owned execution status and sanitized error code first. Check queue age, worker availability, provider errors, and budgets. Never add raw model inputs, bearer tokens, or database URLs to incident logs.

## Backups and retention

Back up PostgreSQL with an encrypted managed backup or `pg_dump` through a restricted administrative environment. Never commit dumps. Include executions, audit records, checkpoint tables and source metadata. Verify restoration into an isolated environment and rerun authorization/recovery tests before accepting it.

Define retention with the data owner. Delete expired terminal execution records, their checkpoint namespaces, and associated audit records according to policy. Use the installed LangGraph checkpointer deletion API after verifying its version-specific semantics. Do not remove active checkpoints. Vacuum/analyze after significant deletion.

## Embedding changes

Changing models or dimensions requires a migration/reindex plan. Dimensions are currently fixed at 1536 and rejected otherwise. The content version includes model and dimensions, preventing unchanged text from silently retaining an old embedding. Retrieval filters on embedding model. Build and validate the new index before switching traffic; never mix vector spaces.

## Secrets

Rotate any key exposed in chat or another shared surface. Update the secret store/local ignored environment and restart affected services. Revoke the old key after the replacement is verified. Do not copy credentials into README examples, issues, reports, shell arguments, or Docker build arguments.
