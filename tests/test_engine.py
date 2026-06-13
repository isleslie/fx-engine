from datetime import timedelta

import pytest

from fxengine.engine import compute_consensus, reject_outliers, to_mids, update_reliability
from fxengine.engine.normalize import SourceMid
from fxengine.engine.reliability import weight_factor
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

    def test_single_tier_confidence_is_capped(self):
        # A tight, deep, single-mechanism panel can no longer score near-perfect:
        # one mechanism, however clean, is capped (no cross-tier corroboration).
        panel = [mid(s, r) for s, r in [("a", 1500), ("b", 1501), ("c", 1499),
                                         ("d", 1500), ("e", 1502), ("f", 1498)]]
        consensus, _ = compute_consensus(panel)
        # within_quality (~0.97) × single-tier cap (0.7); never exceeds the cap.
        assert 0.6 < consensus.confidence <= 0.7
        assert 1498 <= consensus.rate <= 1502
        assert consensus.n_sources == 6
        assert consensus.inter_tier_spread_pct is None  # only one tier present

    def test_two_agreeing_tiers_beat_one_tight_tier(self):
        # Two independent mechanisms that agree should out-score a single tight one.
        survey = [mid(s, r, tier=Tier.AGGREGATOR)
                  for s, r in [("a", 1500), ("b", 1501), ("c", 1499)]]
        p2p = [mid(s, r, tier=Tier.P2P)
               for s, r in [("x", 1500), ("y", 1501), ("z", 1499)]]
        two_tier, _ = compute_consensus(survey + p2p)
        one_tier, _ = compute_consensus(survey)
        assert two_tier.confidence > one_tier.confidence
        assert two_tier.confidence > 0.7  # exceeds the single-tier cap
        assert two_tier.inter_tier_spread_pct == pytest.approx(0.0, abs=0.05)

    def test_within_tier_rejection_isolated_across_tiers(self):
        # The lone P2P price must NOT be evicted by a tight survey pack — the
        # single-pool bug. Each tier rejects only within itself.
        survey = [mid(s, r, tier=Tier.AGGREGATOR)
                  for s, r in [("a", 1500), ("b", 1501), ("c", 1499)]]
        p2p = [mid("p2p", 1384, tier=Tier.P2P)]
        consensus, rejected = compute_consensus(survey + p2p)
        assert "p2p" not in [m.source for m in rejected]
        # P2P tier present and contributes its own sub-consensus.
        p2p_tier = next(t for t in consensus.tiers if t.tier is Tier.P2P)
        assert p2p_tier.rate == pytest.approx(1384, abs=0.5)
        # 50/50 blend sits between the two mechanisms.
        assert 1384 < consensus.rate < 1500

    def test_structural_inter_tier_spread_lowers_confidence(self):
        # A persistent survey↔P2P gap is surfaced and damps cross-tier agreement.
        survey = [mid(s, r, tier=Tier.AGGREGATOR)
                  for s, r in [("a", 1500), ("b", 1500), ("c", 1500)]]
        p2p = [mid(s, r, tier=Tier.P2P) for s, r in [("x", 1380), ("y", 1380)]]
        consensus, _ = compute_consensus(survey + p2p)
        assert consensus.inter_tier_spread_pct == pytest.approx(-8.0, abs=0.2)
        assert consensus.confidence < 0.3  # ~8% gap >> 3% tolerance

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

    def test_reliability_pulls_rate_toward_trusted_source(self):
        panel = [mid("a", 1500), mid("b", 1520)]
        base, _ = compute_consensus(panel)  # equal (prior) reliability
        weighted, _ = compute_consensus(panel, reliability={"a": 1.0, "b": 0.0})
        assert base.rate == pytest.approx(1510, abs=0.5)
        assert weighted.rate < base.rate  # trusted a=1500 carries more weight

    def test_uniform_reliability_leaves_rate_unchanged(self):
        panel = [mid("a", 1500), mid("b", 1520)]
        base, _ = compute_consensus(panel)
        same, _ = compute_consensus(panel, reliability={"a": 0.5, "b": 0.5})
        assert same.rate == pytest.approx(base.rate)


class TestReliabilityScore:
    def test_perfect_match_rises_from_prior(self):
        assert update_reliability(0.5, 0.0) == pytest.approx(0.55)  # 0.9*0.5 + 0.1*1

    def test_max_error_decays(self):
        assert update_reliability(0.5, 0.02) == pytest.approx(0.45)  # quality 0

    def test_score_clamped_to_unit_interval(self):
        assert 0.0 <= update_reliability(0.0, 1.0) <= 1.0
        assert 0.0 <= update_reliability(1.0, 0.0) <= 1.0

    def test_weight_factor_spans_half_to_one(self):
        assert weight_factor(0.0) == pytest.approx(0.5)
        assert weight_factor(1.0) == pytest.approx(1.0)
