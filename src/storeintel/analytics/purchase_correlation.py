from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from storeintel.db.models import Event, Purchase


@dataclass(frozen=True)
class PosTransaction:
    transaction_id: str
    purchase_amount: float
    purchase_timestamp: datetime


@dataclass(frozen=True)
class PurchaseMatch:
    visitor_id: str
    transaction_id: str
    purchase_amount: float
    purchase_timestamp: datetime
    matched_on: datetime


def _parse_timestamp(value: str) -> datetime:
    s = value.strip()
    if not s:
        raise ValueError("empty timestamp")

    # Support 'Z' suffix
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # Common CSV timestamp formats
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M",
        ):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                dt = None  # type: ignore[assignment]
        if dt is None:
            raise

    # Ensure tz-aware
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def read_pos_transactions_csv(
    csv_path: str | Path,
    *,
    transaction_id_col: str = "transaction_id",
    amount_col: str = "purchase_amount",
    timestamp_col: str = "purchase_timestamp",
) -> list[PosTransaction]:
    """Read POS transactions from a CSV file.

    Required columns by default:
      - transaction_id
      - purchase_amount
      - purchase_timestamp

    Returns a list sorted by purchase_timestamp.
    """

    path = Path(csv_path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")

        out: list[PosTransaction] = []
        for row in reader:
            tid = (row.get(transaction_id_col) or "").strip()
            if not tid:
                continue

            ts_raw = row.get(timestamp_col)
            if ts_raw is None:
                raise ValueError(f"Missing column: {timestamp_col}")
            ts = _parse_timestamp(ts_raw)

            amt_raw = row.get(amount_col)
            if amt_raw is None:
                raise ValueError(f"Missing column: {amount_col}")
            amt = float(str(amt_raw).strip())

            out.append(PosTransaction(transaction_id=tid, purchase_amount=amt, purchase_timestamp=ts))

    out.sort(key=lambda t: t.purchase_timestamp)
    return out


def _iter_billing_enters_from_event_dicts(
    events: Iterable[Mapping[str, object]],
    *,
    billing_zone_id: str = "BILLING_ZONE",
    enter_event_types: Sequence[str] = ("zone_enter",),
) -> list[tuple[str, datetime]]:
    enters: list[tuple[str, datetime]] = []
    for ev in events:
        zone_id = ev.get("zone_id")
        if zone_id != billing_zone_id:
            continue
        event_type = ev.get("event_type") or ev.get("event_name")
        if event_type not in enter_event_types:
            continue

        visitor_id = ev.get("visitor_id") or ev.get("track_id")
        if visitor_id is None:
            continue

        ts = ev.get("timestamp")
        if ts is None:
            continue
        if isinstance(ts, str):
            ts_dt = _parse_timestamp(ts)
        elif isinstance(ts, datetime):
            ts_dt = ts
            if ts_dt.tzinfo is None or ts_dt.tzinfo.utcoffset(ts_dt) is None:
                ts_dt = ts_dt.replace(tzinfo=timezone.utc)
        else:
            continue

        enters.append((str(visitor_id), ts_dt))

    enters.sort(key=lambda x: x[1])
    return enters


def correlate_purchases(
    *,
    transactions: Sequence[PosTransaction],
    billing_enters: Sequence[tuple[str, datetime]],
    window: timedelta = timedelta(minutes=5),
) -> list[PurchaseMatch]:
    """Correlate POS transactions to visitors.

    Rule:
      If a visitor enters BILLING_ZONE and a transaction occurs within `window`, associate.

    Matching heuristic when multiple visitors qualify:
      - choose the visitor with the most recent billing-enter time before the transaction.

    Returns PurchaseMatch list (one per matched transaction).
    """

    if window.total_seconds() < 0:
        raise ValueError("window must be non-negative")

    # Ensure sorted
    txs = sorted(transactions, key=lambda t: t.purchase_timestamp)
    enters = sorted(billing_enters, key=lambda x: x[1])

    matches: list[PurchaseMatch] = []

    # Sweep pointer through enters for each transaction
    enter_idx = 0
    active: list[tuple[str, datetime]] = []

    for tx in txs:
        # Move all enters that occurred up to tx time into active list
        while enter_idx < len(enters) and enters[enter_idx][1] <= tx.purchase_timestamp:
            active.append(enters[enter_idx])
            enter_idx += 1

        # Drop active enters that are too old
        cutoff = tx.purchase_timestamp - window
        active = [e for e in active if e[1] >= cutoff]

        if not active:
            continue

        # Pick most recent entry
        visitor_id, entered_at = max(active, key=lambda e: e[1])
        matches.append(
            PurchaseMatch(
                visitor_id=visitor_id,
                transaction_id=tx.transaction_id,
                purchase_amount=tx.purchase_amount,
                purchase_timestamp=tx.purchase_timestamp,
                matched_on=entered_at,
            )
        )

    return matches


def correlate_purchases_from_events(
    *,
    pos_csv_path: str | Path,
    visitor_events: Iterable[Mapping[str, object]],
    billing_zone_id: str = "BILLING_ZONE",
    window_minutes: int = 5,
    enter_event_types: Sequence[str] = ("zone_enter",),
    transaction_id_col: str = "transaction_id",
    amount_col: str = "purchase_amount",
    timestamp_col: str = "purchase_timestamp",
) -> list[PurchaseMatch]:
    """Convenience wrapper: read POS CSV + correlate against in-memory event dicts."""

    transactions = read_pos_transactions_csv(
        pos_csv_path,
        transaction_id_col=transaction_id_col,
        amount_col=amount_col,
        timestamp_col=timestamp_col,
    )
    billing_enters = _iter_billing_enters_from_event_dicts(
        visitor_events,
        billing_zone_id=billing_zone_id,
        enter_event_types=enter_event_types,
    )
    return correlate_purchases(
        transactions=transactions,
        billing_enters=billing_enters,
        window=timedelta(minutes=window_minutes),
    )


def correlate_purchases_from_db(
    *,
    session: Session,
    pos_csv_path: str | Path,
    store_id: str | None = None,
    camera_id: str | None = None,
    billing_zone_id: str = "BILLING_ZONE",
    window_minutes: int = 5,
    enter_event_types: Sequence[str] = ("zone_enter",),
    transaction_id_col: str = "transaction_id",
    amount_col: str = "purchase_amount",
    timestamp_col: str = "purchase_timestamp",
) -> list[PurchaseMatch]:
    """Read POS CSV and correlate against events stored in SQLite."""

    transactions = read_pos_transactions_csv(
        pos_csv_path,
        transaction_id_col=transaction_id_col,
        amount_col=amount_col,
        timestamp_col=timestamp_col,
    )

    if not transactions:
        return []

    min_ts = transactions[0].purchase_timestamp - timedelta(minutes=window_minutes)
    max_ts = transactions[-1].purchase_timestamp

    stmt = select(Event.visitor_id, Event.timestamp).where(
        Event.zone_id == billing_zone_id,
        Event.event_type.in_(list(enter_event_types)),
        Event.timestamp >= min_ts,
        Event.timestamp <= max_ts,
    )
    if store_id:
        stmt = stmt.where(Event.store_id == store_id)
    if camera_id:
        stmt = stmt.where(Event.camera_id == camera_id)

    rows = session.execute(stmt).all()
    enters = [(str(v), t) for (v, t) in rows]
    return correlate_purchases(
        transactions=transactions,
        billing_enters=enters,
        window=timedelta(minutes=window_minutes),
    )


def create_purchase_records(
    *,
    session: Session,
    matches: Sequence[PurchaseMatch],
) -> dict[str, int]:
    """Persist purchase matches into the `purchases` table.

    Deduplicates on transaction_id via unique constraint.

    Returns counts: {"inserted": n, "duplicates": n}
    """

    inserted = 0
    duplicates = 0

    for m in matches:
        try:
            session.add(
                Purchase(
                    visitor_id=m.visitor_id,
                    transaction_id=m.transaction_id,
                    purchase_amount=m.purchase_amount,
                    purchase_timestamp=m.purchase_timestamp,
                )
            )
            session.flush()
            inserted += 1
        except Exception:
            session.rollback()
            # Best-effort duplicate detection: transaction_id is unique.
            duplicates += 1

    session.commit()
    return {"inserted": inserted, "duplicates": duplicates}
