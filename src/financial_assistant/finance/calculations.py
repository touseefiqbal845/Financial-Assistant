from decimal import ROUND_HALF_UP, Decimal

from financial_assistant.contracts.models import FinancialRecord


class IncompatibleValues(ValueError):
    pass


def percentage_change(before: Decimal, after: Decimal) -> Decimal | None:
    if before == 0:
        return None
    return ((after - before) / abs(before) * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)


def compare_periods(records: tuple[FinancialRecord, ...]) -> dict[str, str | None]:
    if len(records) != 2:
        raise IncompatibleValues("Exactly two reporting periods are required.")
    a, b = sorted(records, key=lambda item: item.period)
    keys = ("entity", "currency", "scale", "designation")
    if any(getattr(a, key) != getattr(b, key) for key in keys) or a.period == b.period:
        raise IncompatibleValues(
            "Entity, currency, scale, designation, and periods must be compatible."
        )
    before, after = a.revenue - a.expenses, b.revenue - b.expenses
    change = percentage_change(before, after)
    return {
        "before_period": a.period,
        "after_period": b.period,
        "before_profit": str(before),
        "after_profit": str(after),
        "profit_change": str(after - before),
        "profit_change_percent": str(change) if change is not None else None,
        "revenue_change": str(b.revenue - a.revenue),
        "expense_change": str(b.expenses - a.expenses),
        "currency": a.currency,
        "scale": a.scale,
        "designation": a.designation,
    }
