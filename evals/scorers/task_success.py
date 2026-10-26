def score(answer: dict, case: dict) -> dict[str, bool]:
    return {
        "status": answer["status"] == case["expected_status"],
        "required_facts": all(
            text.lower() in answer["text"].lower() for text in case["required_text"]
        ),
        "citation_integrity": all(
            set(claim["evidence_ids"]) <= {e["id"] for e in answer["evidence"]}
            for claim in answer["claims"]
        ),
    }
