"""Security tests for AST parsing and QuerySpace authorization."""

from __future__ import annotations

import pytest

from querysmith.authorization import (
    AmbiguousColumnError,
    ColumnOperationNotAllowedError,
    MultipleStatementError,
    RelationshipViolationError,
    SelectStarNotAllowedError,
    SQLAuthorizer,
    SQLParseError,
    SQLParser,
    UnauthorizedColumnError,
    UnauthorizedJoinError,
    UnauthorizedTableError,
    UnsupportedStatementError,
)
from querysmith.models import (
    ColumnAccess,
    ColumnSpec,
    ExecutionPolicy,
    JoinType,
    RelationshipSpec,
    ResolvedQuerySpace,
    TableRef,
    TableSpec,
)
from querysmith.semantic import ColumnCapabilities

PERSON = TableRef("Person", "Person")
ACTIVITY = TableRef("Activity", "PersonActivity")


def _space(
    *,
    policy: ExecutionPolicy | None = None,
    relationship_strict: bool = True,
) -> ResolvedQuerySpace:
    return ResolvedQuerySpace(
        [
            TableSpec(
                PERSON,
                [
                    ColumnSpec("BusinessEntityID", "int", False),
                    ColumnSpec(
                        "FirstName",
                        "nvarchar",
                        False,
                        capabilities=ColumnCapabilities(
                            groupable=False,
                            aggregatable=False,
                            joinable=False,
                        ),
                    ),
                    ColumnSpec(
                        "NationalIDNumber",
                        "nvarchar",
                        False,
                        allowed=False,
                    ),
                    ColumnSpec(
                        "IsDeleted",
                        "bit",
                        False,
                        access=ColumnAccess.POLICY_ONLY,
                    ),
                    ColumnSpec(
                        "CreatedAt",
                        "datetime2",
                        False,
                        capabilities=ColumnCapabilities(
                            filterable=False,
                            groupable=False,
                            aggregatable=False,
                            joinable=False,
                        ),
                    ),
                ],
            ),
            TableSpec(
                ACTIVITY,
                [
                    ColumnSpec("PersonID", "int", False),
                    ColumnSpec(
                        "ActivityType",
                        "nvarchar",
                        False,
                        capabilities=ColumnCapabilities(
                            sortable=False,
                            aggregatable=False,
                            joinable=False,
                        ),
                    ),
                    ColumnSpec("Amount", "decimal", False),
                    ColumnSpec(
                        "IsDeleted",
                        "bit",
                        False,
                        access=ColumnAccess.POLICY_ONLY,
                    ),
                ],
            ),
        ],
        [
            RelationshipSpec(
                PERSON,
                "BusinessEntityID",
                ACTIVITY,
                "PersonID",
                strict=relationship_strict,
            )
        ],
        policy or ExecutionPolicy(),
    )


def _authorize(sql: str, space: ResolvedQuerySpace | None = None):
    return SQLAuthorizer().authorize(SQLParser().parse(sql), space or _space())


def test_parser_accepts_select_cte_subquery_and_set_operations() -> None:
    for sql in (
        "SELECT p.FirstName FROM Person.Person p",
        "WITH x AS (SELECT p.FirstName FROM Person.Person p) SELECT x.FirstName FROM x",
        "SELECT x.FirstName FROM (SELECT p.FirstName FROM Person.Person p) x",
        (
            "SELECT p.FirstName FROM Person.Person p UNION ALL "
            "SELECT p.FirstName FROM Person.Person p"
        ),
        (
            "SELECT p.FirstName FROM Person.Person p EXCEPT "
            "SELECT p.FirstName FROM Person.Person p"
        ),
        (
            "SELECT p.FirstName FROM Person.Person p INTERSECT "
            "SELECT p.FirstName FROM Person.Person p"
        ),
    ):
        _authorize(sql)


def test_parser_rejects_invalid_multiple_write_into_comment_and_external_sql() -> None:
    with pytest.raises(SQLParseError):
        SQLParser().parse("SELECT (")
    with pytest.raises(MultipleStatementError):
        SQLParser().parse("SELECT 1; SELECT 2")
    with pytest.raises(MultipleStatementError):
        SQLParser().parse("SELECT 1; DELETE FROM dbo.Users")
    for sql in (
        "DELETE FROM dbo.Users",
        "UPDATE dbo.Users SET Id = 1",
        "SELECT Id INTO dbo.Copy FROM dbo.Users",
        "SELECT /* hidden */ 1",
        "SELECT x.Id FROM OPENQUERY(server, 'SELECT Id FROM t') x",
        "SELECT OBJECT_ID('dbo.Users')",
        "SELECT @@VERSION",
    ):
        with pytest.raises(UnsupportedStatementError):
            SQLParser().parse(sql)


def test_table_authorization_is_schema_aware_and_checks_every_union_branch() -> None:
    _authorize("SELECT p.FirstName FROM Person.Person AS p")
    for sql in (
        "SELECT p.FirstName FROM Sales.Person AS p",
        "SELECT FirstName FROM Person",
        "SELECT p.FirstName FROM master.Person.Person AS p",
        (
            "SELECT p.FirstName FROM Person.Person p UNION ALL "
            "SELECT s.Secret FROM Finance.Salaries s"
        ),
    ):
        with pytest.raises(UnauthorizedTableError):
            _authorize(sql)


def test_unqualified_table_requires_explicit_policy_and_unambiguous_match() -> None:
    permissive = _space(policy=ExecutionPolicy(allow_unqualified_tables=True))
    _authorize("SELECT FirstName FROM Person", permissive)


def test_cte_name_is_not_confused_with_a_physical_table() -> None:
    sql = (
        "WITH Person AS (SELECT p.FirstName FROM Person.Person p) "
        "SELECT Person.FirstName FROM Person"
    )
    _authorize(sql)


@pytest.mark.parametrize(
    ("sql", "operation"),
    [
        ("SELECT p.NationalIDNumber FROM Person.Person p", None),
        (
            "SELECT p.FirstName FROM Person.Person p WHERE p.CreatedAt > '2020-01-01'",
            "FILTER",
        ),
        (
            "SELECT p.FirstName FROM Person.Person p GROUP BY p.FirstName",
            "GROUP",
        ),
        (
            "SELECT SUM(p.FirstName) FROM Person.Person p",
            "AGGREGATE",
        ),
        (
            (
                "SELECT a.ActivityType FROM Activity.PersonActivity a "
                "ORDER BY a.ActivityType"
            ),
            "SORT",
        ),
    ],
)
def test_column_capabilities_are_operation_specific(
    sql: str, operation: str | None
) -> None:
    error = (
        UnauthorizedColumnError if operation is None else ColumnOperationNotAllowedError
    )
    with pytest.raises(error, match=operation):
        _authorize(sql)


def test_having_requires_filter_and_aggregate_capabilities() -> None:
    sql = (
        "SELECT a.PersonID FROM Activity.PersonActivity a "
        "GROUP BY a.PersonID HAVING SUM(a.Amount) > 10"
    )
    report = _authorize(sql)
    amount = next(item for item in report.referenced_columns if item.column == "Amount")
    assert {item.value for item in amount.operations} == {"FILTER", "AGGREGATE"}


@pytest.mark.parametrize(
    "function",
    (
        "SUM(a.Amount)",
        "AVG(a.Amount)",
        "MIN(a.Amount)",
        "MAX(a.Amount)",
        "COUNT(a.Amount)",
        "COUNT(DISTINCT a.Amount)",
    ),
)
def test_aggregate_functions_require_aggregatable_columns(function: str) -> None:
    report = _authorize(f"SELECT {function} FROM Activity.PersonActivity a")
    amount = next(item for item in report.referenced_columns if item.column == "Amount")
    assert "AGGREGATE" in {item.value for item in amount.operations}

    with pytest.raises(ColumnOperationNotAllowedError, match="AGGREGATE"):
        _authorize(
            "SELECT "
            + function.replace("a.Amount", "a.ActivityType")
            + " FROM Activity.PersonActivity a"
        )


def test_expressions_case_functions_and_arithmetic_authorize_leaf_columns() -> None:
    for sql in (
        "SELECT CONCAT('', p.FirstName) FROM Person.Person p",
        (
            "SELECT CASE WHEN p.FirstName = 'A' THEN p.FirstName ELSE '' END "
            "FROM Person.Person p"
        ),
        "SELECT a.Amount + 1 FROM Activity.PersonActivity a",
    ):
        _authorize(sql)
    with pytest.raises(UnauthorizedColumnError):
        _authorize("SELECT CONCAT('', p.NationalIDNumber) FROM Person.Person p")


def test_window_partition_uses_group_and_order_uses_sort() -> None:
    sql = (
        "SELECT ROW_NUMBER() OVER (PARTITION BY a.ActivityType "
        "ORDER BY a.PersonID) AS rn FROM Activity.PersonActivity a"
    )
    report = _authorize(sql)
    activity = next(
        item for item in report.referenced_columns if item.column == "ActivityType"
    )
    person_id = next(
        item for item in report.referenced_columns if item.column == "PersonID"
    )
    assert "GROUP" in {item.value for item in activity.operations}
    assert "SORT" in {item.value for item in person_id.operations}


def test_ambiguity_is_fail_closed_and_order_alias_resolves_lineage() -> None:
    with pytest.raises(AmbiguousColumnError):
        _authorize(
            "SELECT IsDeleted FROM Person.Person p "
            "JOIN Activity.PersonActivity a "
            "ON p.BusinessEntityID = a.PersonID"
        )
    with pytest.raises(ColumnOperationNotAllowedError, match="SORT"):
        _authorize(
            "SELECT a.ActivityType AS kind FROM Activity.PersonActivity a ORDER BY kind"
        )


def test_cte_and_derived_aliases_do_not_bypass_column_access() -> None:
    for sql in (
        (
            "WITH x AS (SELECT p.NationalIDNumber AS Value FROM Person.Person p) "
            "SELECT x.Value FROM x"
        ),
        (
            "SELECT x.Value FROM (SELECT p.NationalIDNumber AS Value "
            "FROM Person.Person p) x"
        ),
        "SELECT p.IsDeleted FROM Person.Person p",
    ):
        with pytest.raises(UnauthorizedColumnError):
            _authorize(sql)


def test_strict_relationship_accepts_both_directions_and_rejects_wrong_join() -> None:
    for condition in (
        "p.BusinessEntityID = a.PersonID",
        "a.PersonID = p.BusinessEntityID",
    ):
        report = _authorize(
            "SELECT p.FirstName, a.ActivityType FROM Person.Person p "
            f"JOIN Activity.PersonActivity a ON {condition}"
        )
        assert len(report.relationships) == 1
    with pytest.raises(RelationshipViolationError):
        _authorize(
            "SELECT p.FirstName, a.ActivityType FROM Person.Person p "
            "JOIN Activity.PersonActivity a ON p.BusinessEntityID = a.Amount"
        )


def test_non_strict_or_unlisted_join_requires_explicit_policy() -> None:
    with pytest.raises(RelationshipViolationError):
        _authorize(
            "SELECT p.FirstName, a.ActivityType FROM Person.Person p "
            "JOIN Activity.PersonActivity a ON p.BusinessEntityID = a.PersonID",
            _space(relationship_strict=False),
        )
    permissive = _space(
        relationship_strict=False,
        policy=ExecutionPolicy(allow_unlisted_joins=True),
    )
    _authorize(
        "SELECT p.FirstName, a.ActivityType FROM Person.Person p "
        "JOIN Activity.PersonActivity a ON p.BusinessEntityID = a.PersonID",
        permissive,
    )


def test_join_shape_policy_rejects_or_non_equality_cross_apply_and_comma() -> None:
    for sql in (
        (
            "SELECT p.FirstName FROM Person.Person p JOIN Activity.PersonActivity a "
            "ON p.BusinessEntityID = a.PersonID OR a.Amount = 0"
        ),
        (
            "SELECT p.FirstName FROM Person.Person p JOIN Activity.PersonActivity a "
            "ON p.BusinessEntityID > a.PersonID"
        ),
        "SELECT p.FirstName FROM Person.Person p CROSS JOIN Activity.PersonActivity a",
        "SELECT p.FirstName FROM Person.Person p, Activity.PersonActivity a",
        (
            "SELECT p.FirstName FROM Person.Person p CROSS APPLY "
            "(SELECT a.PersonID FROM Activity.PersonActivity a) x"
        ),
    ):
        with pytest.raises(UnauthorizedJoinError):
            _authorize(sql)


def test_explicit_cross_policy_does_not_silently_enable_implicit_join() -> None:
    cross_space = _space(
        policy=ExecutionPolicy(allowed_join_types=(JoinType.INNER, JoinType.CROSS))
    )
    _authorize(
        "SELECT p.FirstName FROM Person.Person p CROSS JOIN Activity.PersonActivity a",
        cross_space,
    )
    with pytest.raises(UnauthorizedJoinError):
        _authorize(
            "SELECT p.FirstName FROM Person.Person p, Activity.PersonActivity a",
            cross_space,
        )


def test_correlated_subquery_requires_the_strict_relationship() -> None:
    sql = (
        "SELECT p.FirstName FROM Person.Person p WHERE EXISTS ("
        "SELECT 1 FROM Activity.PersonActivity a "
        "WHERE a.PersonID = p.BusinessEntityID)"
    )
    report = _authorize(sql)
    assert len(report.relationships) == 1
    with pytest.raises(RelationshipViolationError):
        _authorize(
            "SELECT p.FirstName FROM Person.Person p WHERE EXISTS ("
            "SELECT 1 FROM Activity.PersonActivity a "
            "WHERE a.ActivityType = p.FirstName)"
        )


def test_select_star_policy_and_count_star_are_distinct() -> None:
    _authorize("SELECT COUNT(*) FROM Person.Person p")
    for sql in (
        "SELECT * FROM Person.Person p",
        "SELECT p.* FROM Person.Person p",
        "SELECT COUNT(p.*) FROM Person.Person p",
    ):
        with pytest.raises(SelectStarNotAllowedError):
            _authorize(sql)

    safe_star = ResolvedQuerySpace(
        [TableSpec(TableRef("dbo", "Safe"), [ColumnSpec("Id", "int", False)])],
        execution_policy=ExecutionPolicy(allow_select_star=True),
    )
    _authorize("SELECT * FROM dbo.Safe", safe_star)
    _authorize("SELECT s.* FROM dbo.Safe AS s", safe_star)

    denied_star = ResolvedQuerySpace(
        [
            TableSpec(
                TableRef("dbo", "Safe"),
                [
                    ColumnSpec("Id", "int", False),
                    ColumnSpec("Secret", "nvarchar", False, allowed=False),
                ],
            )
        ],
        execution_policy=ExecutionPolicy(allow_select_star=True),
    )
    with pytest.raises(SelectStarNotAllowedError):
        _authorize("SELECT * FROM dbo.Safe", denied_star)
