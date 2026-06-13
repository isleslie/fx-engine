"""Independence guard: detect copycat survey sources.

Many Naira aggregators republish each other (or a shared dealer board), so a
tight survey cluster can be one number wearing several hats — which would inflate
both the consensus weight of that number and the confidence score. Over a window
of recent runs, any pair of survey sources whose mids are effectively identical
in most of the runs they share is flagged correlated; the consensus then halves
the weight of the lower-reliability member so a duplicated quote counts once, not
twice. This is a within-survey-tier concern (the transaction-based tier is a
different mechanism), so only survey history is examined.
"""

from __future__ import annotations


def flag_correlated_pairs(
    history: dict[str, dict[str, float]],
    *,
    tol: float,
    threshold: float,
    min_runs: int,
) -> list[tuple[str, str]]:
    """Return correlated (source_a, source_b) pairs, names sorted within each pair.

    `history` is {source: {run_key: mid}}. A pair is flagged when, across the runs
    both reported (at least `min_runs` of them), the fraction whose mids agree to
    within relative `tol` exceeds `threshold`.
    """
    sources = sorted(history)
    pairs: list[tuple[str, str]] = []
    for i, a in enumerate(sources):
        for b in sources[i + 1:]:
            runs_a, runs_b = history[a], history[b]
            shared = runs_a.keys() & runs_b.keys()
            if len(shared) < min_runs:
                continue
            matches = 0
            for r in shared:
                va, vb = runs_a[r], runs_b[r]
                denom = (va + vb) / 2.0
                if denom > 0 and abs(va - vb) / denom <= tol:
                    matches += 1
            if matches / len(shared) > threshold:
                pairs.append((a, b))
    return pairs
