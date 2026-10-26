import re

from financial_assistant.contracts.models import Claim, Evidence, FinancialRecord
from financial_assistant.finance.calculations import compare_periods


class UnsupportedClaim(ValueError):
    pass


def numeric_tokens(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text.replace(",", "")))


def validate_claims(
    claims: tuple[Claim, ...], evidence: tuple[Evidence, ...], records: tuple[FinancialRecord, ...]
) -> None:
    sources = {item.id: item for item in evidence}
    calculation = compare_periods(records) if len(records) == 2 else {}
    for claim in claims:
        if not set(claim.evidence_ids) <= sources.keys():
            raise UnsupportedClaim("Claim refers to evidence that was not retrieved.")
        allowed = numeric_tokens(" ".join(sources[key].content for key in claim.evidence_ids))
        allowed |= numeric_tokens(str(calculation))
        if not numeric_tokens(claim.text) <= allowed:
            raise UnsupportedClaim("Claim contains a number absent from evidence and calculations.")


def financial_claim(records: tuple[FinancialRecord, ...]) -> Claim:
    result = compare_periods(records)
    percent = result["profit_change_percent"]
    suffix = (
        f" ({percent}%)" if percent is not None else " (percentage change undefined: zero baseline)"
    )
    return Claim(
        text=(
            f"Profit changed from {result['currency']} {result['before_profit']} in {result['before_period']} "
            f"to {result['currency']} {result['after_profit']} in {result['after_period']}; "
            f"change {result['profit_change']}{suffix}. "
            f"Revenue changed by {result['revenue_change']}; expenses changed by {result['expense_change']}. "
            f"Scale: {result['scale']}; designation: {result['designation']}."
        ),
        evidence_ids=tuple(record.evidence_id for record in records),
    )
