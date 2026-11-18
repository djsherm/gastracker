"""Application settings from public TOML configuration and environment variables."""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Settings:
    name: str
    timezone: ZoneInfo
    log_level: str
    database_path: Path
    web_host: str
    web_port: int


def load_settings() -> Settings:
    config_path = Path(os.environ.get("GASTRACKER_CONFIG", "config.toml"))
    with config_path.open("rb") as config_file:
        config = tomllib.load(config_file)

    app = config.get("app", {})
    database = config.get("database", {})
    web = config.get("web", {})
    return Settings(
        name=os.environ.get("APP_NAME", app.get("name", "Gas Spending Tracker")),
        timezone=ZoneInfo(os.environ.get("APP_TIMEZONE", app.get("timezone", "America/Toronto"))),
        log_level=os.environ.get("APP_LOG_LEVEL", app.get("log_level", "INFO")),
        database_path=Path(os.environ.get("DATABASE_PATH", database.get("path", "/data/gas.db"))),
        web_host=os.environ.get("WEB_HOST", web.get("host", "127.0.0.1")),
        web_port=int(os.environ.get("WEB_PORT", web.get("port", 8000))),
    )
