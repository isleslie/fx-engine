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
    http_timeout_seconds: float = 15.0
    user_agent: str = "fx-engine/0.1 (personal research; +https://github.com/CHANGE_ME/fx-engine)"


settings = Settings()
