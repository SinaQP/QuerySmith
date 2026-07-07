"""Tests for QuerySmith configuration loading."""

from pytest import MonkeyPatch

from querysmith.config import load_config


def test_config_parses_trusted_flag(monkeypatch: MonkeyPatch) -> None:
    """The DB_TRUSTED_CONNECTION flag should parse common true values."""

    monkeypatch.setenv("DB_SERVER", "localhost")
    monkeypatch.setenv("DB_DATABASE", "QuerySmith")
    monkeypatch.setenv("DB_USERNAME", "querysmith_user")
    monkeypatch.setenv("DB_PASSWORD", "secret")
    monkeypatch.setenv("DB_TRUSTED_CONNECTION", "true")

    cfg = load_config()

    assert cfg.trusted_connection is True
