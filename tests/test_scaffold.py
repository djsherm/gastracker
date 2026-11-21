import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfoNotFoundError

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from gastracker.config import load_settings
from gastracker.db import create_database_engine
from gastracker.main import create_app


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    for variable in (
        "APP_NAME",
        "APP_TIMEZONE",
        "APP_LOG_LEVEL",
        "DATABASE_PATH",
        "INBOX_DATABASE_PATH",
        "WEB_HOST",
        "WEB_PORT",
    ):
        monkeypatch.delenv(variable, raising=False)
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[app]\nname = "Test tracker"\ntimezone = "America/Toronto"\n'
        '[web]\nhost = "127.0.0.1"\nport = 8000\n'
        '[database]\npath = "unused.db"\n'
    )
    monkeypatch.setenv("GASTRACKER_CONFIG", str(config_path))


def test_health():
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "timezone": "America/Toronto"}


def test_environment_overrides_toml(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_NAME", "Override")
    monkeypatch.setenv("APP_TIMEZONE", "UTC")
    monkeypatch.setenv("APP_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "gas.db"))
    monkeypatch.setenv("INBOX_DATABASE_PATH", str(tmp_path / "inbox.db"))
    monkeypatch.setenv("WEB_HOST", "localhost")
    monkeypatch.setenv("WEB_PORT", "9000")
    settings = load_settings()
    assert settings.name == "Override"
    assert settings.timezone.key == "UTC"
    assert settings.log_level == "DEBUG"
    assert settings.database_path == tmp_path / "gas.db"
    assert settings.inbox_database_path == tmp_path / "inbox.db"
    assert settings.web_host == "localhost"
    assert settings.web_port == 9000


def test_toronto_timezone_handles_daylight_saving():
    timezone = load_settings().timezone
    assert datetime(2026, 1, 1, tzinfo=timezone).utcoffset().total_seconds() == -18000
    assert datetime(2026, 7, 1, tzinfo=timezone).utcoffset().total_seconds() == -14400


def test_invalid_timezone_fails_at_startup(monkeypatch):
    monkeypatch.setenv("APP_TIMEZONE", "invalid/timezone")
    with pytest.raises(ZoneInfoNotFoundError):
        create_app()


def test_database_connection(monkeypatch, tmp_path):
    database_path = tmp_path / "data" / "gas.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    engine = create_database_engine(load_settings())
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
            assert connection.execute(text("PRAGMA journal_mode")).scalar_one() == "wal"
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert database_path.exists()
    finally:
        engine.dispose()


def test_inbox_path_defaults_beside_overridden_database(monkeypatch, tmp_path):
    database_path = tmp_path / "custom" / "gas.sqlite"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    settings = load_settings()
    assert settings.inbox_database_path == database_path.with_name("inbox.db")


def test_alembic_scaffold(monkeypatch, tmp_path):
    database_path = tmp_path / "migrations" / "gas.db"
    inbox_database_path = tmp_path / "migrations" / "inbox.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("INBOX_DATABASE_PATH", str(inbox_database_path))
    command.upgrade(Config("alembic.ini"), "head")
    command.check(Config("alembic.ini"))
    assert database_path.exists()
    assert inbox_database_path.exists()

    engine = create_database_engine(load_settings())
    try:
        with engine.begin() as connection, pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO merchant_rules "
                    "(pattern, match_type, category, priority, enabled) "
                    "VALUES ('bad', 'unknown', 'gas', 0, 1)"
                )
            )
    finally:
        engine.dispose()

    with sqlite3.connect(inbox_database_path) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='seen_nonces'"
        ).fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO inbox "
                "(received_at, raw_body, notified_at, processed, dedupe_key) "
                "VALUES ('now', 'body', 'now', 2, 'key')"
            )
