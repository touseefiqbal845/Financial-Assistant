# Verification — October 26, 2026

## Completed

| Check | Observed result |
|---|---|
| Locked dependency installation | Installed from `uv.lock` |
| Ruff lint and formatting | Passed |
| Mypy | Passed for 29 source modules |
| Full pytest suite, including real PostgreSQL | 40 passed; no skipped tests in the full database-enabled run |
| Coverage | 84% overall in that run |
| Deterministic evaluations | Four of four cases passed |
| PostgreSQL + pgvector | Real vector insertion/search, idempotent re-ingestion, source RLS and reader write denial passed |
| Checkpoint recovery | Closed/reopened PostgreSQL checkpointer and resumed after planning successfully |
| Docker image | Built with locked dependencies and pre-cached tokenizer |
| Container identity | Non-root UID/GID `10001:10001` |
| Image secrets | `/app/.env` absent; no credentials supplied as build arguments |
| API container smoke | Health/readiness, missing authentication, cross-entity denial, submission and cancellation passed |
| Separate worker container | Completed a persisted clarification job using the real database/checkpointer, with zero model calls |
| Tracked-file secret scan | Passed; local `.env` is ignored |
| OpenAI account preflight | Key authenticated; configured model identifiers were listed |

The code has been exercised on Windows Python 3.12 and in Linux containers. The source-role integration tests use explicit fixture vectors; these are not evidence of semantic embedding quality.

## Demonstrated fixture examples

1. SQL plus document explanation: Q1 profit PKR 300,000; Q2 profit PKR 200,000; change -33.33%. Source references preserved, management explanation labeled as such.
2. Missing periods: clarification without a model request.
3. Missing financial record: insufficient evidence rather than an invented result.
4. Document service failure: numeric partial result and explicit missing explanation.
5. Unauthorized entity: HTTP 403 before execution creation.
6. Agent attempts a tool outside its role: dispatcher denial; supplied instructions cannot expand the tool registry or scope.
7. Running cancellation: task interrupted and execution marked cancelled.

## Live-model blocker

The first paid embedding request returned HTTP 429 with `credit_balance_exhausted`. The supplied key authenticates, but the API account has no remaining credit. No end-to-end live financial answer or semantic retrieval evaluation passed. No successful model token usage was recorded; an actual billing invoice was not inspected. Do not interpret fixture results as live-model accuracy.

After adding API credit, stop the worker, seed documents, and run the bounded live evaluation documented in the README. Inspect both financial accuracy and semantic source support. Do not silently substitute models.

## Delivery and production limits

The project is prepared locally. GitHub publication requires an authenticated GitHub account and an explicit destination/visibility. No live financial service was deployed publicly.

Production release still requires identity-provider claim configuration, deployment-specific rate limits, backups/restore validation, retention configuration, expanded adversarial and human-reviewed financial evaluations, and representative load tests. Coverage is evidence of exercised paths, not a guarantee of security or correctness.
