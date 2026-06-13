"""Runtime configuration. All values overridable via FX_* environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root, so file defaults resolve whether run from source or installed editable.
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FX_", env_file=".env", extra="ignore")

    db_path: Path = Path("data/fx.db")
    currencies: list[str] = ["USD", "GBP", "EUR"]
    # Config-driven Tier-1 survey sources (one YAML entry instead of a module).
    # The Docker image ships this at /app/config and sets FX_SOURCE_REGISTRY.
    source_registry: Path = _REPO_ROOT / "config" / "source_registry.yaml"
    ingest_interval_minutes: int = 30
    use_mock_sources: bool = True  # flip to False once live adapters land
    # Consensus tuning
    freshness_half_life_minutes: float = 90.0
    mad_k: float = 3.5  # outlier cut in scaled-MAD units
    # Tier-aware consensus: blend weight per source mechanism, renormalised over
    # the tiers actually present in a run (a tier with no surviving source is
    # simply absent, so survey-only currencies fall back cleanly). Keys are the
    # Tier values from models.py. 0.5/0.5 is a deliberately neutral starting
    # point — see docs/architecture.md for why P2P may later earn a higher share.
    tier_weights: dict[str, float] = {
        "tier1_aggregator": 0.5,
        "tier2_p2p": 0.5,
        "tier3_fintech": 0.5,
    }
    # Per-source reliability (slow EWMA of how close a source sits to its tier
    # sub-consensus). Modulates within-tier weight by (0.5 + reliability/2), so
    # it scales a source between 0.5x and 1.0x — never zeroes it.
    reliability_alpha: float = 0.1  # EWMA learning rate
    reliability_error_max: float = 0.02  # 2% error => zero reliability credit
    reliability_prior: float = 0.5  # neutral starting score for a new source
    http_timeout_seconds: float = 15.0
    user_agent: str = "fx-engine/0.1 (personal research; +https://github.com/CHANGE_ME/fx-engine)"


settings = Settings()
