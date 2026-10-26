from decimal import Decimal

import pytest

from financial_assistant.contracts.models import FinancialRecord
from financial_assistant.finance.calculations import (
    IncompatibleValues,
    compare_periods,
    percentage_change,
)


def record(period, revenue, expenses, **changes):
    return FinancialRecord(
        evidence_id=period,
        entity="acme",
        period=period,
        currency="PKR",
        scale="units",
        designation="actual",
        revenue=Decimal(revenue),
        expenses=Decimal(expenses),
    ).model_copy(update=changes)


def test_profit_decline_is_not_revenue_decline():
    result = compare_periods(
        (record("2026-Q1", "1000000", "700000"), record("2026-Q2", "1100000", "900000"))
    )
    assert result["profit_change"] == "-100000"
    assert result["profit_change_percent"] == "-33.33"
    assert result["revenue_change"] == "100000"
    assert result["expense_change"] == "200000"


@pytest.mark.parametrize(
    "before,after,expected",
    [("0", "10", None), ("-100", "-50", "50.00"), ("3", "4", "33.33"), ("1", "1.00005", "0.01")],
)
def test_percentage_conventions(before, after, expected):
    value = percentage_change(Decimal(before), Decimal(after))
    assert value == (None if expected is None else Decimal(expected))


@pytest.mark.parametrize(
    "change",
    [
        {"currency": "USD"},
        {"scale": "millions"},
        {"entity": "beta"},
        {"designation": "forecast"},
        {"period": "2026-Q1"},
    ],
)
def test_incompatible_values_are_rejected(change):
    with pytest.raises(IncompatibleValues):
        compare_periods(
            (record("2026-Q1", "10", "5"), record("2026-Q2", "12", "6").model_copy(update=change))
        )
