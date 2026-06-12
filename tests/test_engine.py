from datetime import timedelta

import pytest

from fxengine.engine import compute_consensus, reject_outliers, to_mids
from fxengine.engine.normalize import SourceMid
from fxengine.models import Observation, Side, Tier, utcnow

NOW = utcnow()


def obs(source, rate, side=Side.MID, ccy="USD", tier=Tier.AGGREGATOR, at=NOW):
    return Observation(source, tier, ccy, side, rate, at)


def mid(source, rate, ccy="USD", at=NOW, tier=Tier.AGGREGATOR):
    return SourceMid(source, tier, ccy, rate, at)


class TestNormalize:
    def test_buy_sell_collapse_to_average(self):
        mids = to_mids([obs("a", 1490, Side.BUY), obs("a", 1510, Side.SELL)])
        assert len(mids) == 1
        assert mids[0].mid == 1500

    def test_single_side_taken_as_is(self):
        mids = to_mids([obs("p2p", 1505, Side.MID, tier=Tier.P2P)])
        assert mids[0].mid == 1505

    def test_official_excluded(self):
        mids = to_mids([obs("cbn", 1400, tier=Tier.OFFICIAL), obs("a", 1500)])
        assert [m.source for m in mids] == ["a"]

    def test_currencies_kept_separate(self):
        mids = to_mids([obs("a", 1500), obs("a", 1900, ccy="GBP")])
        assert len(mids) == 2


class TestOutliers:
    def test_clear_outlier_rejected(self):
        panel = [mid("a", 1500), mid("b", 1502), mid("c", 1499), mid("wild", 1700)]
        kept, rejected = reject_outliers(panel)
        assert [m.source for m in rejected] == ["wild"]
        assert len(kept) == 3

    def test_small_panel_keeps_everything(self):
        panel = [mid("a", 1500), mid("b", 1700)]
        kept, rejected = reject_outliers(panel)
        assert len(kept) == 2 and not rejected

    def test_zero_mad_uses_relative_tolerance(self):
        # Three identical + one 5% off: MAD is 0, the 5% source must still go.
        panel = [mid("a", 1500), mid("b", 1500), mid("c", 1500), mid("d", 1575)]
        kept, rejected = reject_outliers(panel)
        assert [m.source for m in rejected] == ["d"]

    def test_never_rejects_below_two_survivors(self):
        panel = [mid("a", 1500), mid("b", 1500), mid("c", 2000)]
        kept, rejected = reject_outliers(panel)
        assert len(kept) >= 2


class TestConsensus:
    def test_empty_returns_none(self):
        consensus, rejected = compute_consensus([])
        assert consensus is None and rejected == []

    def test_mixed_currencies_raise(self):
        with pytest.raises(ValueError):
            compute_consensus([mid("a", 1500), mid("b", 1900, ccy="GBP")])

    def test_tight_fresh_panel_high_confidence(self):
        panel = [mid(s, r) for s, r in [("a", 1500), ("b", 1501), ("c", 1499),
                                         ("d", 1500), ("e", 1502), ("f", 1498)]]
        consensus, _ = compute_consensus(panel)
        assert consensus.confidence > 0.9
        assert 1498 <= consensus.rate <= 1502
        assert consensus.n_sources == 6

    def test_outlier_excluded_from_rate(self):
        panel = [mid("a", 1500), mid("b", 1501), mid("c", 1499), mid("wild", 1800)]
        consensus, rejected = compute_consensus(panel)
        assert consensus.n_rejected == 1
        assert [m.source for m in rejected] == ["wild"]
        assert consensus.rate < 1510  # the 1800 didn't drag the average

    def test_stale_source_downweighted(self):
        stale_at = NOW - timedelta(hours=12)
        panel = [mid("fresh1", 1500), mid("fresh2", 1500), mid("stale", 1530, at=stale_at)]
        consensus, _ = compute_consensus(panel)
        # Unweighted mean would be 1510; freshness decay must pull it well below.
        assert consensus.rate < 1505

    def test_wide_disagreement_low_confidence(self):
        panel = [mid("a", 1450), mid("b", 1500), mid("c", 1560), mid("d", 1410)]
        consensus, _ = compute_consensus(panel)
        assert consensus.confidence < 0.5

    def test_confidence_bounded(self):
        panel = [mid("a", 1500), mid("b", 1500), mid("c", 1500),
                 mid("d", 1500), mid("e", 1500), mid("f", 1500)]
        consensus, _ = compute_consensus(panel)
        assert 0.0 <= consensus.confidence <= 1.0
