"""Configuration management for Argus."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    """Application settings loaded from environment variables."""

    # Model configuration
    argus_model: str = "claude-sonnet-4-6"

    # Watchtower endpoints (direct backend access)
    watchtower_loki_url: str = "http://localhost:3100"
    watchtower_tempo_url: str = "http://localhost:3200"
    watchtower_prometheus_url: str = "http://localhost:9090"

    # SonarQube
    sonarqube_url: str = "http://localhost:9000"
    sonarqube_token: str = ""

    # GitHub (optional)
    github_token: str = ""

    # Paths
    db_path: Path = Path.home() / ".argus" / "argus.db"
    runs_dir: Path = Path("runs")
    lessons_dir: Path = Path("lessons")

    @classmethod
    def load(cls) -> "Settings":
        """Load settings from environment variables."""
        return cls(
            argus_model=os.getenv("ARGUS_MODEL", cls.argus_model),
            watchtower_loki_url=os.getenv("WATCHTOWER_LOKI_URL", cls.watchtower_loki_url),
            watchtower_tempo_url=os.getenv("WATCHTOWER_TEMPO_URL", cls.watchtower_tempo_url),
            watchtower_prometheus_url=os.getenv(
                "WATCHTOWER_PROMETHEUS_URL", cls.watchtower_prometheus_url
            ),
            sonarqube_url=os.getenv("SONARQUBE_URL", cls.sonarqube_url),
            sonarqube_token=os.getenv("SONARQUBE_TOKEN", ""),
            github_token=os.getenv("GITHUB_TOKEN", ""),
        )

    def ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.lessons_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance - loaded once at startup
settings = Settings.load()
