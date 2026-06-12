"""Outlier rejection: median + scaled MAD.

MAD (median absolute deviation) is robust to exactly the failure modes we
expect here — a stale page, a fat-fingered quote, a source that drifted off
the pack. Scaled MAD (x1.4826) makes the cut threshold comparable to
standard deviations under normality, so `k=3.5` reads like "3.5 sigma".

Edge cases handled explicitly:
- n < 3: too few sources to call anything an outlier; keep all.
- MAD == 0 (sources identical or near-identical): fall back to a relative
  tolerance around the median rather than rejecting everything that differs
  in the 4th decimal.
"""

from __future__ import annotations

import numpy as np

from .normalize import SourceMid

MAD_SCALE = 1.4826
_ZERO_MAD_REL_TOL = 0.01  # 1% band around median when MAD collapses


def reject_outliers(
    mids: list[SourceMid], k: float = 3.5
) -> tuple[list[SourceMid], list[SourceMid]]:
    """Split mids into (kept, rejected). All inputs must share one currency."""
    if len(mids) < 3:
        return list(mids), []

    rates = np.array([m.mid for m in mids], dtype=float)
    med = float(np.median(rates))
    mad = float(np.median(np.abs(rates - med))) * MAD_SCALE

    kept: list[SourceMid] = []
    rejected: list[SourceMid] = []
    for m, r in zip(mids, rates, strict=True):
        if mad > 0:
            is_outlier = abs(r - med) / mad > k
        else:
            is_outlier = abs(r - med) / med > _ZERO_MAD_REL_TOL
        (rejected if is_outlier else kept).append(m)

    # Never reject our way below a usable panel.
    if len(kept) < 2:
        return list(mids), []
    return kept, rejected
