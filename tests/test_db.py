"""Tests for QuerySmith database helpers."""

from querysmith.config import DBConfig
from querysmith.db import build_url


def test_build_url_sql_auth() -> None:
    """SQL authentication should include UID and PWD."""

    config = DBConfig(
        server="localhost",
        database="QuerySmith",
        username="querysmith_user",
        password="secret",
    )

    odbc_string = build_url(config).query["odbc_connect"]

    assert "UID=querysmith_user;" in odbc_string
    assert "PWD=secret;" in odbc_string
    assert "Trusted_Connection" not in odbc_string


def test_build_url_trusted() -> None:
    """Trusted authentication should omit UID and PWD."""

    config = DBConfig(
        server="localhost",
        database="QuerySmith",
        username="querysmith_user",
        password="secret",
        trusted_connection=True,
    )

    odbc_string = build_url(config).query["odbc_connect"]

    assert "Trusted_Connection=yes;" in odbc_string
    assert "UID=" not in odbc_string
    assert "PWD=" not in odbc_string


def test_build_url_named_instance() -> None:
    """SQL Server instance names should be preserved in the ODBC string."""

    config = DBConfig(
        server=r"localhost\SQLEXPRESS",
        database="QuerySmith",
        username="querysmith_user",
        password="secret",
    )

    odbc_string = build_url(config).query["odbc_connect"]

    assert r"SERVER=localhost\SQLEXPRESS;" in odbc_string
