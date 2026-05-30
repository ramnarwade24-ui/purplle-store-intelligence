from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from storeintel.db.models import Event


@dataclass(frozen=True)
class FunnelStep:
    step: str
    visitors: int


def compute_funnel(events: Iterable[Event], steps: list[str]) -> list[FunnelStep]:
    # Minimal funnel: visitor counts that achieved each step (unordered within window).
    by_visitor: dict[str, set[str]] = defaultdict(set)
    for e in events:
        if not e.visitor_id:
            continue
        by_visitor[e.visitor_id].add(e.event_type)

    results: list[FunnelStep] = []
    eligible = set(by_visitor.keys())
    for step in steps:
        eligible = {vid for vid in eligible if step in by_visitor[vid]}
        results.append(FunnelStep(step=step, visitors=len(eligible)))
    return results
