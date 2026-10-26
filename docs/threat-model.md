# Threat model

Protected assets: credentials, tenant financial records, document content, execution results, checkpoints, and API spend.

Trust boundaries: browser/client to API; signed identity claims to execution scope; model outputs to dispatcher; database/document text to model context; worker to external model provider; application roles to migration/ingestion roles.

| Threat | Control | Remaining limit |
|---|---|---|
| Cross-tenant data access | Signed OIDC scope, tool checks, SQL predicates, source RLS | Identity-provider claim issuance and backend credentials remain trusted |
| Prompt injection in a document | Data cannot register tools, change scope, or supply SQL; tool allowlists | Model prose may still be misleading; semantic evaluations are required |
| Fabricated financial arithmetic | Decimal functions and deterministic final numerical summary | Incorrect source records are still incorrect inputs |
| Forged citations | Reference validation against retrieved authorized evidence | Existing reference does not prove semantic support |
| Resource exhaustion | Request/context/tool/model/time budgets and bounded concurrency | Configure ingress rate limits and admission quotas for production |
| Credential leakage | Ignored local environment, redacted application logs, no secrets in images | Operators must protect host files, backups, provider and tracing settings |
| Job duplication | Leases, stable thread IDs, checkpoints, read-only tools | Provider calls can repeat after a crash; no exactly-once billing claim |
| Malicious ingestion | Admin-only interface, path/type/size/page limits | PDF parsers require patching and isolation for hostile uploads |
| Sensitive checkpoints | Authenticated execution ownership, backend-only database access | Storage encryption, retention and backup access are deployment duties |

Production uses RS256 tokens from a configured HTTPS JWKS endpoint and verifies issuer, audience, expiry, issued-at, subject, tenant, and entities. Do not map editable user profile fields directly to privileged claims. Execution scopes are snapshots; urgent revocation requires cancellation of affected queued/running executions.

No public file-upload endpoint or arbitrary SQL/code tool is provided. Migration and ingestion entry points are administrative. Synthetic seeding is rejected in production.

This document does not certify regulatory compliance or absence of vulnerabilities. Conduct deployment-specific security review before processing real financial records.
