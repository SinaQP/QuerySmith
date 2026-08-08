"""Mandatory policy injection, re-authorization, and audit tests."""

from __future__ import annotations

from types import MappingProxyType

import pytest
from sqlglot import parse_one

from querysmith.authorization import (
    FinalAuthorizationError,
    PolicyInjectionError,
    UnauthorizedColumnError,
)
from querysmith.context import ContextBuilder
from querysmith.models import (
    ColumnAccess,
    ColumnSpec,
    ExecutionPolicy,
    JoinType,
    MandatoryFilterPolicy,
    RelationshipSpec,
    ResolvedQuerySpace,
    TableRef,
    TableSpec,
)
from querysmith.policy import InjectionResult, PolicyEngine, PolicyInjector

PERSON = TableRef("Person", "Person")
ACTIVITY = TableRef("Activity", "PersonActivity")


def _policy_space(*, max_rows: int = 100) -> ResolvedQuerySpace:
    return ResolvedQuerySpace(
        [
            TableSpec(
                PERSON,
                [
                    ColumnSpec("BusinessEntityID", "int", False),
                    ColumnSpec("FirstName", "nvarchar", False),
                    ColumnSpec(
                        "IsDeleted",
                        "bit",
                        False,
                        access=ColumnAccess.POLICY_ONLY,
                    ),
                ],
            ),
            TableSpec(
                ACTIVITY,
                [
                    ColumnSpec("PersonID", "int", False),
                    ColumnSpec("ActivityType", "nvarchar", False),
                    ColumnSpec(
                        "IsDeleted",
                        "bit",
                        False,
                        access=ColumnAccess.POLICY_ONLY,
                    ),
                ],
            ),
        ],
        [RelationshipSpec(PERSON, "BusinessEntityID", ACTIVITY, "PersonID")],
        ExecutionPolicy(
            max_rows=max_rows,
            mandatory_filters=(
                MandatoryFilterPolicy(PERSON, "IsDeleted", "=", False),
                MandatoryFilterPolicy(ACTIVITY, "IsDeleted", "=", False),
            ),
        ),
    )


def test_policy_only_columns_are_hidden_and_rejected_in_generated_sql() -> None:
    space = _policy_space()
    assert "IsDeleted" not in ContextBuilder().build(space)
    with pytest.raises(UnauthorizedColumnError, match="reserved"):
        PolicyEngine().authorize_and_apply(
            "SELECT p.IsDeleted FROM Person.Person p", space
        )


def test_mandatory_filter_is_parameterized_and_row_limit_is_ast_based() -> None:
    result = PolicyEngine().authorize_and_apply(
        "SELECT p.FirstName FROM Person.Person p", _policy_space(max_rows=25)
    )

    assert "TOP 25" in result.sql
    assert "p.IsDeleted = :qs_policy_0_0" in result.sql
    assert dict(result.parameters) == {"qs_policy_0_0": False}
    assert result.is_authorized is True
    assert result.original_sql == "SELECT p.FirstName FROM Person.Person p"
    assert PERSON in result.referenced_tables


def test_existing_where_or_precedence_is_preserved() -> None:
    result = PolicyEngine().authorize_and_apply(
        "SELECT p.FirstName FROM Person.Person p "
        "WHERE p.FirstName = 'A' OR p.FirstName = 'B'",
        _policy_space(),
    )

    assert "(p.FirstName = 'A' OR p.FirstName = 'B') AND p.IsDeleted" in result.sql


def test_left_join_policy_is_injected_into_on_not_where() -> None:
    result = PolicyEngine().authorize_and_apply(
        "SELECT p.FirstName, a.ActivityType FROM Person.Person p "
        "LEFT JOIN Activity.PersonActivity a "
        "ON p.BusinessEntityID = a.PersonID",
        _policy_space(),
    )

    on_text, where_text = result.sql.split(" WHERE ", maxsplit=1)
    assert "a.IsDeleted = :qs_policy_1_1" in on_text
    assert "p.IsDeleted = :qs_policy_0_0" in where_text
    assert "a.IsDeleted" not in where_text


def test_policies_apply_inside_cte_and_subquery_scopes() -> None:
    for sql in (
        "WITH x AS (SELECT p.FirstName FROM Person.Person p) SELECT x.FirstName FROM x",
        "SELECT x.FirstName FROM (SELECT p.FirstName FROM Person.Person p) x",
    ):
        result = PolicyEngine().authorize_and_apply(sql, _policy_space())
        assert "p.IsDeleted = :qs_policy_0_0" in result.sql


def test_set_operation_is_limited_once_and_each_branch_receives_policy() -> None:
    result = PolicyEngine().authorize_and_apply(
        "SELECT p.FirstName FROM Person.Person p UNION ALL "
        "SELECT p2.FirstName FROM Person.Person p2",
        _policy_space(max_rows=12),
    )

    assert result.sql.count("IsDeleted") == 2
    assert result.sql.count("TOP 12") == 1
    assert dict(result.parameters) == {
        "qs_policy_0_0": False,
        "qs_policy_0_1": False,
    }


def test_right_or_full_join_policy_injection_fails_closed() -> None:
    space = ResolvedQuerySpace(
        _policy_space().tables,
        _policy_space().relationships,
        ExecutionPolicy(
            allowed_join_types=(JoinType.INNER, JoinType.LEFT, JoinType.RIGHT),
            mandatory_filters=_policy_space().execution_policy.mandatory_filters,
        ),
    )

    with pytest.raises(PolicyInjectionError, match="join semantics"):
        PolicyEngine().authorize_and_apply(
            "SELECT p.FirstName, a.ActivityType FROM Person.Person p "
            "RIGHT JOIN Activity.PersonActivity a "
            "ON p.BusinessEntityID = a.PersonID",
            space,
        )


def test_self_join_applies_policy_to_every_occurrence() -> None:
    employee = TableRef("Person", "Employee")
    space = ResolvedQuerySpace(
        [
            TableSpec(
                employee,
                [
                    ColumnSpec("EmployeeID", "int", False),
                    ColumnSpec("ManagerID", "int", True),
                    ColumnSpec("Name", "nvarchar", False),
                    ColumnSpec(
                        "IsDeleted",
                        "bit",
                        False,
                        access=ColumnAccess.POLICY_ONLY,
                    ),
                ],
            )
        ],
        [RelationshipSpec(employee, "ManagerID", employee, "EmployeeID")],
        ExecutionPolicy(
            mandatory_filters=(
                MandatoryFilterPolicy(employee, "IsDeleted", "=", False),
            )
        ),
    )

    result = PolicyEngine().authorize_and_apply(
        "SELECT e.Name, m.Name FROM Person.Employee e "
        "LEFT JOIN Person.Employee m ON e.ManagerID = m.EmployeeID",
        space,
    )

    assert "m.IsDeleted = :qs_policy_0_1" in result.sql
    assert "e.IsDeleted = :qs_policy_0_0" in result.sql
    assert len(result.parameters) == 2


def test_policy_injection_is_sql_idempotent() -> None:
    space = _policy_space()
    engine = PolicyEngine()
    first = engine.authorize_and_apply("SELECT p.FirstName FROM Person.Person p", space)
    parsed = engine.parser.parse(first.sql)
    second = PolicyInjector().apply(parsed, space)

    assert second.expression.sql(dialect="tsql") == first.sql


def test_existing_equivalent_mandatory_literal_is_not_duplicated() -> None:
    customer = TableRef("Sales", "Customer")
    space = ResolvedQuerySpace(
        [
            TableSpec(
                customer,
                [
                    ColumnSpec("CustomerId", "int", False),
                    ColumnSpec("IsDeleted", "bit", False),
                ],
            )
        ],
        execution_policy=ExecutionPolicy(
            mandatory_filters=(
                MandatoryFilterPolicy(customer, "IsDeleted", "=", False),
            )
        ),
    )

    result = PolicyEngine().authorize_and_apply(
        "SELECT c.CustomerId FROM Sales.Customer c WHERE c.IsDeleted = 0",
        space,
    )

    assert result.sql.count("IsDeleted") == 1
    assert dict(result.parameters) == {}


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT p.FirstName FROM Person.Person p", "TOP 10"),
        ("SELECT TOP 50 p.FirstName FROM Person.Person p", "TOP 10"),
        ("SELECT TOP 5 p.FirstName FROM Person.Person p", "TOP 5"),
    ],
)
def test_row_limit_adds_reduces_or_preserves_top(sql: str, expected: str) -> None:
    result = PolicyEngine().authorize_and_apply(sql, _policy_space(max_rows=10))
    assert expected in result.sql


def test_scalar_count_does_not_need_top_but_receives_row_policy() -> None:
    result = PolicyEngine().authorize_and_apply(
        "SELECT COUNT(*) FROM Person.Person p", _policy_space(max_rows=10)
    )
    assert "TOP" not in result.sql
    assert "p.IsDeleted = :qs_policy_0_0" in result.sql


def test_final_authorization_rejects_a_malicious_injector() -> None:
    class MaliciousInjector:
        def apply(self, parsed, query_space):  # type: ignore[no-untyped-def]
            expression = parse_one(
                "SELECT s.Secret FROM Finance.Salaries s", read="tsql"
            )
            return InjectionResult(
                expression,
                MappingProxyType({}),
                ("malicious",),
                frozenset(),
            )

    engine = PolicyEngine(injector=MaliciousInjector())  # type: ignore[arg-type]
    with pytest.raises(FinalAuthorizationError):
        engine.authorize_and_apply(
            "SELECT p.FirstName FROM Person.Person p", _policy_space()
        )


def test_final_authorization_does_not_trust_policy_column_in_projection() -> None:
    class LeakingInjector:
        def apply(self, parsed, query_space):  # type: ignore[no-untyped-def]
            expression = parse_one(
                "SELECT p.IsDeleted FROM Person.Person p", read="tsql"
            )
            return InjectionResult(
                expression,
                MappingProxyType({}),
                ("malicious",),
                frozenset({(PERSON.identity_key, "isdeleted")}),
            )

    engine = PolicyEngine(injector=LeakingInjector())  # type: ignore[arg-type]
    with pytest.raises(FinalAuthorizationError):
        engine.authorize_and_apply(
            "SELECT p.FirstName FROM Person.Person p", _policy_space()
        )


def test_final_authorization_rejects_an_extra_allowed_column() -> None:
    class ExpandingInjector:
        def apply(self, parsed, query_space):  # type: ignore[no-untyped-def]
            expression = parse_one(
                "SELECT p.FirstName, p.BusinessEntityID FROM Person.Person p",
                read="tsql",
            )
            return InjectionResult(
                expression,
                MappingProxyType({}),
                ("malicious",),
                frozenset(),
            )

    engine = PolicyEngine(injector=ExpandingInjector())  # type: ignore[arg-type]
    with pytest.raises(FinalAuthorizationError, match="physical columns"):
        engine.authorize_and_apply(
            "SELECT p.FirstName FROM Person.Person p", _policy_space()
        )
