"""Runtime configuration. All values overridable via FX_* environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FX_", env_file=".env", extra="ignore")

    db_path: Path = Path("data/fx.db")
    currencies: list[str] = ["USD", "GBP", "EUR"]
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
    http_timeout_seconds: float = 15.0
    user_agent: str = "fx-engine/0.1 (personal research; +https://github.com/CHANGE_ME/fx-engine)"


settings = Settings()
