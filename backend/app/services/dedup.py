"""Per-user duplicate / merge-suggestion engine.

Strategy:
  1. Exact barcode match  -> strong duplicate (score 1.0)
  2. Otherwise fuzzy on brand + item_name, gated by weight agreement.
All comparisons are scoped to a single user's record set.
"""
from __future__ import annotations

from itertools import combinations

from rapidfuzz import fuzz

from app.models import ItemRecord
from app.schemas.imdb import MergeCandidate

_FUZZY_THRESHOLD = 0.85


def _weight_matches(a: ItemRecord, b: ItemRecord) -> bool:
    if a.weight_value is None or b.weight_value is None:
        return True  # unknown weight doesn't veto a match
    if a.weight_unit != b.weight_unit:
        return False
    return abs(a.weight_value - b.weight_value) < 1e-6


def _fuzzy_score(a: ItemRecord, b: ItemRecord) -> float:
    brand = fuzz.WRatio(a.brand or "", b.brand or "") / 100.0
    name = fuzz.WRatio(a.item_name or "", b.item_name or "") / 100.0
    return round(0.5 * brand + 0.5 * name, 3)


def find_duplicates(records: list[ItemRecord]) -> list[MergeCandidate]:
    candidates: list[MergeCandidate] = []
    for a, b in combinations(records, 2):
        # Keep the older record as the canonical target.
        keep, dup = (a, b) if a.id < b.id else (b, a)

        if keep.barcode and dup.barcode and keep.barcode == dup.barcode:
            candidates.append(MergeCandidate(
                record_id=dup.id, duplicate_of=keep.id, score=1.0,
                reason="Identical barcode", matched_fields=["barcode"],
            ))
            continue

        if not _weight_matches(keep, dup):
            continue
        score = _fuzzy_score(keep, dup)
        if score >= _FUZZY_THRESHOLD:
            matched = ["brand", "item_name"]
            if keep.weight_value is not None and dup.weight_value is not None:
                matched.append("weight")
            candidates.append(MergeCandidate(
                record_id=dup.id, duplicate_of=keep.id, score=score,
                reason="Similar brand + product name", matched_fields=matched,
            ))

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates
