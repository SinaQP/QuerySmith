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


def test_config_supports_env_example_names(monkeypatch: MonkeyPatch) -> None:
    """The documented DB_HOST-style variables should load correctly."""

    monkeypatch.setenv("DB_SERVER", "")
    monkeypatch.setenv("DB_DATABASE", "")
    monkeypatch.setenv("DB_USERNAME", "")
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "1433")
    monkeypatch.setenv("DB_NAME", "QuerySmith")
    monkeypatch.setenv("DB_USER", "querysmith_user")
    monkeypatch.setenv("DB_PASSWORD", "secret")

    cfg = load_config()

    assert cfg.server == "localhost,1433"
    assert cfg.database == "QuerySmith"
    assert cfg.username == "querysmith_user"
