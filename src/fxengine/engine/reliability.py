"""Per-source reliability: a slow EWMA of how close each source sits to its own
tier's sub-consensus, so sources earn trust over many runs rather than within one.

After each run, for every participating source:
    error   = |source_mid - tier_sub_consensus| / tier_sub_consensus
              (a source rejected within its tier counts as error = E_MAX)
    quality = max(0, 1 - error / E_MAX)
    score   = (1 - alpha) * score_prev + alpha * quality      (prior 0.5)

The score feeds back as a within-tier weight factor of (0.5 + score/2): a
proven source counts up to 2x a brand-new/erratic one, but none is ever zeroed.
Compared against the source's OWN tier sub-consensus (not the blended rate), so
the structural survey↔P2P gap never penalises a source for its mechanism.
"""

from __future__ import annotations

from ..config import settings


def update_reliability(
    previous: float,
    error: float,
    *,
    alpha: float | None = None,
    error_max: float | None = None,
) -> float:
    """One EWMA step. Returns the new score in [0, 1]."""
    a = alpha if alpha is not None else settings.reliability_alpha
    e_max = error_max if error_max is not None else settings.reliability_error_max
    quality = max(0.0, 1.0 - error / e_max) if e_max > 0 else 0.0
    score = (1.0 - a) * previous + a * quality
    return min(1.0, max(0.0, score))


def weight_factor(reliability: float) -> float:
    """Within-tier multiplicative factor: maps reliability [0,1] -> [0.5, 1.0]."""
    return 0.5 + reliability / 2.0
