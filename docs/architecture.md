# Architecture

The API authenticates and persists a request. A separate worker claims pending work with `FOR UPDATE SKIP LOCKED`. A thirty-second lease is renewed while work runs. A crashed worker leaves a recoverable record. A new worker resumes the persisted LangGraph thread, with a namespace derived from trusted tenant, subject, and execution IDs.

The planner produces a DAG validated against a small supported role set. Retrieval tasks must be independent; exactly one analysis task depends on all retrieval tasks. Execution proceeds in dependency waves. Tasks within a wave run under a semaphore and return isolated results. The node merges their updates once, avoiding ambiguous concurrent writes. The initial supported graph has no recursive subagents and permits one plan correction.

Each specialist gets only its role's permitted tool names. The model returns a structured action; the dispatcher resolves it against an application registry, validates scope, and invokes fixed operations. Specialists can request one operation and observe its result, within a maximum of two action decisions. This deliberately small action space supports the two-period product scope.

`agents` depends on contracts, model ports, and the tool dispatcher. `tools` depends on source ports and deterministic finance functions. `connectors` implements external capabilities. `bootstrap` is the composition root. FastAPI routes do not contain model prompts or SQL.

Financial records remain in relational tables. Document chunks retain content hashes, page numbers, source metadata, model IDs, and 1536-dimensional embeddings. Source queries constrain tenant/entity, periods, and embedding model before results enter model context. pgvector provides cosine ordering. The baseline does not claim calibrated relevance thresholds; retrieval quality must be measured on the target corpus.

Execution contracts are JSON-serializable, version-controlled structures. The final numeric claim is deterministic. Model-produced explanation claims must cite retrieved evidence; numeric tokens must appear in evidence or approved computations. The final composer can select/reorder explanations verbatim. These checks do not prove semantic entailment or causality.

The platform uses one shared OpenAI client per worker with SDK retries disabled. Every transient adapter retry reserves budget separately. Persistent reservations conservatively bound attempted work even after recovery. A worker crash between billing and usage persistence can leave actual usage understated; reservations and provider billing remain the audit backstop. Strict financial spend enforcement requires provider-side caps.

Horizontal scaling starts with additional worker processes. Each claims a different execution; per-execution task concurrency remains bounded. API replicas are stateless. Database pool sizes, provider limits, queue age, and deployment quotas determine safe replica counts. No distributed-scale performance claim is made without load testing.
