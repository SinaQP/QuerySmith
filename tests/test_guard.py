"""Tests for SQL safety guardrails."""

import pytest

from querysmith.guard import UnsafeQueryError, validate_safe_select


def test_accept_simple_select() -> None:
    assert validate_safe_select("SELECT Id FROM dbo.Users") == "SELECT Id FROM dbo.Users"


def test_accept_select_with_trailing_semicolon() -> None:
    assert validate_safe_select("SELECT Id FROM dbo.Users;") == "SELECT Id FROM dbo.Users"


def test_accept_with_cte_select() -> None:
    sql = """
        WITH RecentOrders AS (
            SELECT Id, CustomerId
            FROM dbo.Orders
        )
        SELECT Id
        FROM RecentOrders
    """

    assert validate_safe_select(sql).startswith("WITH RecentOrders")


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "   ",
    ],
)
def test_reject_empty_sql(sql: str) -> None:
    with pytest.raises(UnsafeQueryError):
        validate_safe_select(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM dbo.Users",
        "UPDATE dbo.Users SET Name = 'x'",
        "DROP TABLE dbo.Users",
        "INSERT INTO dbo.Users (Name) VALUES ('x')",
    ],
)
def test_reject_dangerous_write_keywords(sql: str) -> None:
    with pytest.raises(UnsafeQueryError):
        validate_safe_select(sql)


def test_reject_select_into() -> None:
    with pytest.raises(UnsafeQueryError):
        validate_safe_select("SELECT Id INTO dbo.UserCopy FROM dbo.Users")


def test_reject_multiple_statements() -> None:
    with pytest.raises(UnsafeQueryError):
        validate_safe_select("SELECT Id FROM dbo.Users; DROP TABLE dbo.Users")


def test_reject_line_comments() -> None:
    with pytest.raises(UnsafeQueryError):
        validate_safe_select("SELECT Id FROM dbo.Users -- comment")


def test_reject_block_comments() -> None:
    with pytest.raises(UnsafeQueryError):
        validate_safe_select("SELECT Id FROM dbo.Users /* comment */")


def test_reject_exec() -> None:
    with pytest.raises(UnsafeQueryError):
        validate_safe_select("EXEC dbo.GetUsers")


def test_reject_use_database() -> None:
    with pytest.raises(UnsafeQueryError):
        validate_safe_select("USE master")


def test_reject_query_starting_with_non_select_or_with() -> None:
    with pytest.raises(UnsafeQueryError):
        validate_safe_select("DECLARE @x int")


def test_returned_sql_is_stripped_and_trailing_semicolon_removed() -> None:
    assert validate_safe_select("  SELECT Id FROM dbo.Users;  ") == (
        "SELECT Id FROM dbo.Users"
    )
