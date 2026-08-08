"""Tests for SQL safety guardrails."""

import pytest

from querysmith.guard import (
    ColumnOperationNotAllowedError,
    UnsafeQueryError,
    validate_safe_select,
)
from querysmith.models import (
    ColumnSpec,
    RelationshipSpec,
    ResolvedQuerySpace,
    TableRef,
    TableSpec,
)
from querysmith.semantic import ColumnCapabilities


def _query_space() -> ResolvedQuerySpace:
    customer = TableSpec(
        TableRef("Sales", "Customer"),
        [ColumnSpec("CustomerId", "int", False)],
    )
    orders = TableSpec(
        TableRef("Sales", "Orders"),
        [
            ColumnSpec("OrderId", "int", False),
            ColumnSpec("CustomerId", "int", False),
        ],
    )
    return ResolvedQuerySpace(
        [customer, orders],
        [RelationshipSpec(orders.ref, "CustomerId", customer.ref, "CustomerId")],
    )


def test_accept_simple_select() -> None:
    assert (
        validate_safe_select("SELECT Id FROM dbo.Users") == "SELECT Id FROM dbo.Users"
    )


def test_accept_select_with_trailing_semicolon() -> None:
    assert (
        validate_safe_select("SELECT Id FROM dbo.Users;") == "SELECT Id FROM dbo.Users"
    )


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


def test_reject_openquery_external_access() -> None:
    with pytest.raises(UnsafeQueryError):
        validate_safe_select("SELECT * FROM OPENQUERY(RemoteServer, 'SELECT 1')")


def test_reject_query_starting_with_non_select_or_with() -> None:
    with pytest.raises(UnsafeQueryError):
        validate_safe_select("DECLARE @x int")


def test_returned_sql_is_stripped_and_trailing_semicolon_removed() -> None:
    assert validate_safe_select("  SELECT Id FROM dbo.Users;  ") == (
        "SELECT Id FROM dbo.Users"
    )


def test_query_space_accepts_allowed_table_and_join() -> None:
    sql = (
        "SELECT c.CustomerId "
        "FROM Sales.Customer AS c "
        "JOIN Sales.Orders AS o ON o.CustomerId = c.CustomerId"
    )

    assert validate_safe_select(sql, _query_space()) == sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM dbo.Users",
        "SELECT * FROM Marketing.Customer",
        "SELECT * FROM Customer",
        (
            "SELECT c.CustomerId FROM Sales.Customer AS c "
            "JOIN Marketing.Orders AS o ON o.CustomerId = c.CustomerId"
        ),
    ],
)
def test_query_space_rejects_table_outside_scope(sql: str) -> None:
    with pytest.raises(UnsafeQueryError):
        validate_safe_select(sql, _query_space())


def test_query_space_guard_understands_cte_and_subquery_aliases() -> None:
    sql = """
        WITH RecentOrders AS (
            SELECT OrderId, CustomerId
            FROM Sales.Orders
        )
        SELECT nested.CustomerId
        FROM (
            SELECT CustomerId FROM RecentOrders
        ) AS nested
        JOIN Sales.Customer AS c ON c.CustomerId = nested.CustomerId
    """

    assert validate_safe_select(sql, _query_space()).startswith("WITH RecentOrders")


def test_query_space_guard_validates_columns_in_every_clause() -> None:
    sql = (
        "SELECT c.CustomerId, COUNT(o.OrderId) AS OrderCount "
        "FROM Sales.Customer AS c JOIN Sales.Orders AS o "
        "ON o.CustomerId = c.CustomerId "
        "WHERE o.OrderId > 0 GROUP BY c.CustomerId "
        "ORDER BY OrderCount DESC"
    )

    assert validate_safe_select(sql, _query_space()) == sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT c.Secret FROM Sales.Customer AS c",
        "SELECT c.CustomerId FROM Sales.Customer AS c WHERE c.Secret = 1",
        (
            "SELECT c.CustomerId FROM Sales.Customer AS c "
            "JOIN Sales.Orders AS o ON o.Secret = c.CustomerId"
        ),
        "SELECT c.CustomerId FROM Sales.Customer AS c ORDER BY c.Secret",
        "SELECT c.Secret, COUNT(c.CustomerId) FROM Sales.Customer AS c GROUP BY c.Secret",
        "SELECT SUM(c.Secret) FROM Sales.Customer AS c",
        "SELECT * FROM Sales.Customer",
        "SELECT c.* FROM Sales.Customer AS c",
    ],
)
def test_query_space_guard_rejects_unknown_or_wildcard_columns(sql: str) -> None:
    with pytest.raises(UnsafeQueryError):
        validate_safe_select(sql, _query_space())


def _capability_space() -> ResolvedQuerySpace:
    return ResolvedQuerySpace(
        [
            TableSpec(
                TableRef("Sales", "Metrics"),
                [
                    ColumnSpec("Id", "int", False),
                    ColumnSpec(
                        "ProjectionOnly",
                        "int",
                        False,
                        capabilities=ColumnCapabilities(filterable=False),
                    ),
                    ColumnSpec(
                        "Metric",
                        "int",
                        False,
                        capabilities=ColumnCapabilities(
                            sortable=False,
                            groupable=False,
                            aggregatable=False,
                        ),
                    ),
                ],
            ),
            TableSpec(
                TableRef("Sales", "Dimension"),
                [
                    ColumnSpec(
                        "MetricId",
                        "int",
                        False,
                        capabilities=ColumnCapabilities(joinable=False),
                    )
                ],
            ),
        ]
    )


@pytest.mark.parametrize(
    ("sql", "operation"),
    [
        (
            "SELECT m.Id FROM Sales.Metrics AS m WHERE m.ProjectionOnly = 1",
            "FILTER",
        ),
        ("SELECT m.Metric FROM Sales.Metrics AS m ORDER BY m.Metric", "SORT"),
        (
            "SELECT m.Metric FROM Sales.Metrics AS m GROUP BY m.Metric",
            "GROUP",
        ),
        ("SELECT SUM(m.Metric) FROM Sales.Metrics AS m", "AGGREGATE"),
        (
            (
                "SELECT m.Id FROM Sales.Metrics AS m "
                "JOIN Sales.Dimension AS d ON d.MetricId = m.Id"
            ),
            "JOIN",
        ),
    ],
)
def test_query_space_guard_enforces_operation_capabilities(
    sql: str, operation: str
) -> None:
    with pytest.raises(ColumnOperationNotAllowedError, match=operation):
        validate_safe_select(sql, _capability_space())


def test_cte_and_output_alias_cannot_bypass_sort_capability() -> None:
    sql = (
        "WITH values_cte AS ("
        "SELECT m.Metric AS total FROM Sales.Metrics AS m"
        ") SELECT v.total FROM values_cte AS v ORDER BY v.total"
    )

    with pytest.raises(ColumnOperationNotAllowedError, match="SORT"):
        validate_safe_select(sql, _capability_space())


def test_count_star_is_allowed_but_other_wildcards_are_rejected() -> None:
    sql = "SELECT COUNT(*) AS TotalRows FROM Sales.Metrics"
    assert validate_safe_select(sql, _capability_space()) == sql

    for wildcard in (
        "SELECT * FROM Sales.Metrics",
        "SELECT m.* FROM Sales.Metrics AS m",
        "SELECT COUNT(m.*) FROM Sales.Metrics AS m",
    ):
        with pytest.raises(UnsafeQueryError, match=r"COUNT\(\*\)"):
            validate_safe_select(wildcard, _capability_space())
