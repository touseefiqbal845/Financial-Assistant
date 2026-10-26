# Evaluation methodology

Acceptance configuration is versioned before runs. Deterministic fixture cases must all pass. They validate execution plumbing, arithmetic presentation, clarification, partial failure, and citation integrity. They do not measure model quality or semantic retrieval.

Real PostgreSQL tests use fixed vectors explicitly labeled `fixture-embedding`; these establish vector storage, authorization, and query behavior, not embedding relevance. Live seed documents use the configured OpenAI embedding model.

Live smoke evaluation is opt-in, uses synthetic data and account-visible model IDs, and caps per-execution reservations within the selected total budget. Its initial cases cover a grounded comparison and deterministic clarification. This is insufficient for production acceptance by itself.

A production corpus should include human-reviewed expected figures, source passages, missing-data cases, unit/currency mismatches, adversarial instructions, ambiguous questions, and authorized entity scopes. Track numeric accuracy, citation entailment, retrieval recall@k, task success, abstention, denied access, latency, and cost per successful task. Compare against a simpler single-agent baseline.

Human rubric: verify entity and reporting period, reconcile each number, read every cited passage, distinguish reported explanations from proven causes, and reject unsupported claims. If adding model graders, calibrate against these labels and report disagreement; never use a model judge as the sole arithmetic or authorization test.

Persist dataset and prompt hashes, code revision, configuration/model IDs, per-case scores, durations, usage and estimated cost. Reports generated with fixtures must identify themselves as simulated and must not report invented provider token usage.
