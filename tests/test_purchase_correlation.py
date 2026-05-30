from __future__ import annotations

from datetime import datetime, timedelta, timezone

from storeintel.analytics.purchase_correlation import PosTransaction, correlate_purchases


def test_correlate_purchases_picks_most_recent_billing_enter():
    t0 = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)

    billing_enters = [
        ("visitor-a", t0 + timedelta(minutes=0)),
        ("visitor-b", t0 + timedelta(minutes=2)),
    ]

    transactions = [
        PosTransaction(
            transaction_id="tx-1",
            purchase_amount=12.5,
            purchase_timestamp=t0 + timedelta(minutes=4),
        )
    ]

    matches = correlate_purchases(transactions=transactions, billing_enters=billing_enters, window=timedelta(minutes=5))
    assert len(matches) == 1
    assert matches[0].visitor_id == "visitor-b"
    assert matches[0].transaction_id == "tx-1"


def test_correlate_purchases_ignores_outside_window():
    t0 = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)

    billing_enters = [("visitor-a", t0)]
    transactions = [
        PosTransaction(
            transaction_id="tx-1",
            purchase_amount=10.0,
            purchase_timestamp=t0 + timedelta(minutes=6),
        )
    ]

    matches = correlate_purchases(transactions=transactions, billing_enters=billing_enters, window=timedelta(minutes=5))
    assert matches == []
