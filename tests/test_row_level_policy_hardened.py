"""Comprehensive unit and security integration tests for Row-Level Access Policies, Mandatory Filter Injection, and AST-Based SQL Rewriting."""

from __future__ import annotations

from typing import Any

import pytest

from querysmith.authorization import (
    SQLParser,
    UnauthorizedColumnError,
)
from querysmith.exceptions import (
    ConflictingMandatoryFilterError,
    InvalidRuntimeContextValueError,
    MissingRuntimeContextError,
    OuterJoinRewriteError,
)
from querysmith.models import (
    ColumnAccess,
    ColumnSpec,
    ExecutionPolicy,
    FilterOperator,
    JoinType,
    RelationshipSpec,
    RequiredFilter,
    ResolvedQuerySpace,
    TableRef,
    TableSpec,
)
from querysmith.pipeline import execute_authorized_query
from querysmith.policy import PolicyEngine, PolicyInjector, validate_runtime_context

TENANT_TABLE = TableRef("Sales", "Orders")
CUSTOMER_TABLE = TableRef("Sales", "Customers")


def _make_orders_space(
    *, tenant_access: ColumnAccess = ColumnAccess.POLICY_ONLY
) -> ResolvedQuerySpace:
    return ResolvedQuerySpace(
        [
            TableSpec(
                TENANT_TABLE,
                [
                    ColumnSpec("OrderID", "int", False, primary_key=True),
                    ColumnSpec("TenantID", "int", False, access=tenant_access),
                    ColumnSpec("CustomerID", "int", False),
                    ColumnSpec("TotalDue", "decimal", False),
                    ColumnSpec(
                        "IsDeleted", "bit", False, access=ColumnAccess.POLICY_ONLY
                    ),
                ],
                required_filters=[
                    RequiredFilter(column="TenantID", value_from_context="tenant_id"),
                    RequiredFilter(column="IsDeleted", value=False),
                ],
            ),
            TableSpec(
                CUSTOMER_TABLE,
                [
                    ColumnSpec("CustomerID", "int", False, primary_key=True),
                    ColumnSpec("TenantID", "int", False, access=tenant_access),
                    ColumnSpec("Name", "nvarchar", False),
                ],
                required_filters=[
                    RequiredFilter(column="TenantID", value_from_context="tenant_id"),
                ],
            ),
        ],
        relationships=[
            RelationshipSpec(TENANT_TABLE, "CustomerID", CUSTOMER_TABLE, "CustomerID")
        ],
        execution_policy=ExecutionPolicy(
            max_rows=100,
            allow_unlisted_joins=True,
            allowed_join_types=(
                JoinType.INNER,
                JoinType.LEFT,
                JoinType.RIGHT,
                JoinType.FULL,
            ),
        ),
    )


class FakeEngine:
    def __init__(self, raw_rows: list[dict[str, Any]] | None = None) -> None:
        self.raw_rows = (
            raw_rows if raw_rows is not None else [{"OrderID": 1, "TotalDue": 100.0}]
        )
        self.sql = ""
        self.parameters: dict[str, Any] = {}

    def connect(self) -> FakeConnection:
        return FakeConnection(self)


from typing import Self


class FakeConnection:
    def __init__(self, engine: FakeEngine) -> None:
        self.engine = engine

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execution_options(self, **kwargs: Any) -> FakeConnection:
        return self

    def execute(
        self, statement: Any, parameters: dict[str, Any] | None = None
    ) -> FakeResult:
        self.engine.sql = str(statement)
        self.engine.parameters = parameters or {}
        return FakeResult(self.engine.raw_rows)


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> list[dict[str, Any]]:
        return self._rows


# ==============================================================================
# Task 1: Row-Level Access Policy & Runtime Context Validation Tests
# ==============================================================================


def test_missing_runtime_context_key_raises_error() -> None:
    space = _make_orders_space()
    with pytest.raises(MissingRuntimeContextError, match="tenant_id"):
        PolicyEngine().authorize_and_apply(
            "SELECT o.OrderID FROM Sales.Orders o", space, runtime_context={}
        )


def test_scalar_filter_rejects_collection_value() -> None:
    space = _make_orders_space()
    with pytest.raises(InvalidRuntimeContextValueError, match="scalar value"):
        validate_runtime_context(space, {"tenant_id": [1, 2, 3]})


def test_in_operator_requires_collection_value() -> None:
    space = ResolvedQuerySpace(
        [
            TableSpec(
                TENANT_TABLE,
                [
                    ColumnSpec("OrderID", "int", False),
                    ColumnSpec("TenantID", "int", False),
                ],
                required_filters=[
                    RequiredFilter(
                        column="TenantID",
                        operator=FilterOperator.IN,
                        value_from_context="allowed_tenants",
                    )
                ],
            )
        ]
    )
    with pytest.raises(InvalidRuntimeContextValueError, match="collection"):
        validate_runtime_context(space, {"allowed_tenants": 123})


def test_in_operator_rejects_empty_collection() -> None:
    space = ResolvedQuerySpace(
        [
            TableSpec(
                TENANT_TABLE,
                [
                    ColumnSpec("OrderID", "int", False),
                    ColumnSpec("TenantID", "int", False),
                ],
                required_filters=[
                    RequiredFilter(
                        column="TenantID",
                        operator=FilterOperator.IN,
                        value_from_context="allowed_tenants",
                    )
                ],
            )
        ]
    )
    with pytest.raises(InvalidRuntimeContextValueError, match="empty"):
        validate_runtime_context(space, {"allowed_tenants": []})


def test_in_operator_rejects_excessive_collection_limit() -> None:
    space = ResolvedQuerySpace(
        [
            TableSpec(
                TENANT_TABLE,
                [
                    ColumnSpec("OrderID", "int", False),
                    ColumnSpec("TenantID", "int", False),
                ],
                required_filters=[
                    RequiredFilter(
                        column="TenantID",
                        operator=FilterOperator.IN,
                        value_from_context="allowed_tenants",
                    )
                ],
            )
        ]
    )
    with pytest.raises(InvalidRuntimeContextValueError, match="limit of 1000"):
        validate_runtime_context(space, {"allowed_tenants": list(range(1001))})


def test_context_rejects_callable_or_sql_objects() -> None:
    space = _make_orders_space()

    class FakeSQL:
        sql = "1=1"

    with pytest.raises(InvalidRuntimeContextValueError, match="raw SQL fragments"):
        validate_runtime_context(space, {"tenant_id": lambda: 10})

    with pytest.raises(InvalidRuntimeContextValueError, match="raw SQL fragments"):
        validate_runtime_context(space, {"tenant_id": FakeSQL()})


def test_runtime_context_is_not_mutated() -> None:
    space = _make_orders_space()
    original_ctx = {"tenant_id": 42}
    copy_ctx = dict(original_ctx)
    PolicyEngine().authorize_and_apply(
        "SELECT o.OrderID FROM Sales.Orders o", space, runtime_context=original_ctx
    )
    assert original_ctx == copy_ctx


def test_policy_only_column_cannot_be_queried_directly() -> None:
    space = _make_orders_space()
    with pytest.raises(UnauthorizedColumnError):
        PolicyEngine().authorize_and_apply(
            "SELECT o.TenantID FROM Sales.Orders o",
            space,
            runtime_context={"tenant_id": 10},
        )


def test_prompt_injection_does_not_affect_policy_enforcement() -> None:
    space = _make_orders_space()
    user_sql = "SELECT o.OrderID, o.TotalDue FROM Sales.Orders o WHERE 1=1"
    res = PolicyEngine().authorize_and_apply(
        user_sql, space, runtime_context={"tenant_id": 100}
    )
    assert "o.TenantID = :qs_policy_" in res.sql
    assert res.parameters["qs_policy_0_0"] == 100


# ==============================================================================
# Task 2: Mandatory Filter Injection & Parameterization Tests
# ==============================================================================


def test_mandatory_filter_injection_parameterization() -> None:
    space = _make_orders_space()
    res = PolicyEngine().authorize_and_apply(
        "SELECT o.OrderID FROM Sales.Orders o", space, runtime_context={"tenant_id": 55}
    )
    assert "o.TenantID = :qs_policy_0_0" in res.sql
    assert res.parameters["qs_policy_0_0"] == 55


def test_in_operator_ast_injection_and_parameter_mapping() -> None:
    space = ResolvedQuerySpace(
        [
            TableSpec(
                TENANT_TABLE,
                [
                    ColumnSpec("OrderID", "int", False),
                    ColumnSpec(
                        "TenantID", "int", False, access=ColumnAccess.POLICY_ONLY
                    ),
                ],
                required_filters=[
                    RequiredFilter(
                        column="TenantID",
                        operator=FilterOperator.IN,
                        value_from_context="allowed_tenants",
                    )
                ],
            )
        ]
    )
    res = PolicyEngine().authorize_and_apply(
        "SELECT o.OrderID FROM Sales.Orders o",
        space,
        runtime_context={"allowed_tenants": [10, 20, 30]},
    )
    assert (
        "o.TenantID IN (:qs_policy_0_0_p0, :qs_policy_0_0_p1, :qs_policy_0_0_p2)"
        in res.sql
    )
    assert res.parameters == {
        "qs_policy_0_0_p0": 10,
        "qs_policy_0_0_p1": 20,
        "qs_policy_0_0_p2": 30,
    }


def test_existing_where_merged_with_and_precedence() -> None:
    space = _make_orders_space()
    res = PolicyEngine().authorize_and_apply(
        "SELECT o.OrderID FROM Sales.Orders o WHERE o.TotalDue > 500 OR o.TotalDue < 100",
        space,
        runtime_context={"tenant_id": 10},
    )
    assert "(o.TotalDue > 500 OR o.TotalDue < 100) AND" in res.sql
    assert "o.TenantID = :qs_policy_0_0" in res.sql


def test_contradictory_user_predicate_neq_raises_error() -> None:
    space = _make_orders_space(tenant_access=ColumnAccess.USER_ALLOWED)
    with pytest.raises(
        ConflictingMandatoryFilterError, match="contradicts mandatory policy"
    ):
        PolicyEngine().authorize_and_apply(
            "SELECT o.OrderID FROM Sales.Orders o WHERE o.TenantID != 10",
            space,
            runtime_context={"tenant_id": 10},
        )


def test_contradictory_user_predicate_literal_mismatch_raises_error() -> None:
    space = _make_orders_space(tenant_access=ColumnAccess.USER_ALLOWED)
    with pytest.raises(
        ConflictingMandatoryFilterError, match="contradicts mandatory policy"
    ):
        PolicyEngine().authorize_and_apply(
            "SELECT o.OrderID FROM Sales.Orders o WHERE o.TenantID = 999",
            space,
            runtime_context={"tenant_id": 10},
        )


def test_contradictory_user_predicate_is_null_raises_error() -> None:
    space = _make_orders_space(tenant_access=ColumnAccess.USER_ALLOWED)
    with pytest.raises(ConflictingMandatoryFilterError, match="IS NULL"):
        PolicyEngine().authorize_and_apply(
            "SELECT o.OrderID FROM Sales.Orders o WHERE o.TenantID IS NULL",
            space,
            runtime_context={"tenant_id": 10},
        )


def test_self_join_applies_policy_to_all_occurrences() -> None:
    space = ResolvedQuerySpace(
        [
            TableSpec(
                TENANT_TABLE,
                [
                    ColumnSpec("OrderID", "int", False),
                    ColumnSpec("ParentOrderID", "int", True),
                    ColumnSpec(
                        "TenantID", "int", False, access=ColumnAccess.POLICY_ONLY
                    ),
                ],
                required_filters=[
                    RequiredFilter(column="TenantID", value_from_context="tenant_id"),
                ],
            )
        ],
        relationships=[
            RelationshipSpec(TENANT_TABLE, "OrderID", TENANT_TABLE, "ParentOrderID")
        ],
        execution_policy=ExecutionPolicy(allow_unlisted_joins=True),
    )
    res = PolicyEngine().authorize_and_apply(
        "SELECT p.OrderID, c.OrderID FROM Sales.Orders p JOIN Sales.Orders c ON p.OrderID = c.ParentOrderID",
        space,
        runtime_context={"tenant_id": 7},
    )
    assert "p.TenantID = :qs_policy_0_0" in res.sql
    assert "c.TenantID = :qs_policy_0_1" in res.sql
    assert len(res.parameters) == 2


def test_left_join_injects_into_on_clause() -> None:
    space = _make_orders_space()
    res = PolicyEngine().authorize_and_apply(
        "SELECT c.Name, o.OrderID FROM Sales.Customers c LEFT JOIN Sales.Orders o ON c.CustomerID = o.CustomerID",
        space,
        runtime_context={"tenant_id": 5},
    )
    on_text, where_text = res.sql.split(" WHERE ", maxsplit=1)
    assert "o.TenantID = :qs_policy_0_1" in on_text
    assert "c.TenantID = :qs_policy_2_0" in where_text


def test_right_join_fails_closed_with_outer_join_rewrite_error() -> None:
    space = _make_orders_space()
    with pytest.raises(OuterJoinRewriteError, match="RIGHT JOIN"):
        PolicyEngine().authorize_and_apply(
            "SELECT c.Name, o.OrderID FROM Sales.Customers c RIGHT JOIN Sales.Orders o ON c.CustomerID = o.CustomerID",
            space,
            runtime_context={"tenant_id": 5},
        )


def test_full_join_fails_closed_with_outer_join_rewrite_error() -> None:
    space = _make_orders_space()
    with pytest.raises(OuterJoinRewriteError, match="FULL JOIN"):
        PolicyEngine().authorize_and_apply(
            "SELECT c.Name, o.OrderID FROM Sales.Customers c FULL JOIN Sales.Orders o ON c.CustomerID = o.CustomerID",
            space,
            runtime_context={"tenant_id": 5},
        )


def test_cte_and_subquery_scopes_receive_policies() -> None:
    space = _make_orders_space()

    cte_sql = "WITH Recent AS (SELECT o.OrderID, o.TotalDue FROM Sales.Orders o) SELECT r.OrderID FROM Recent r"
    res_cte = PolicyEngine().authorize_and_apply(
        cte_sql, space, runtime_context={"tenant_id": 12}
    )
    assert "o.TenantID = :qs_policy_0_0" in res_cte.sql

    subquery_sql = (
        "SELECT sub.OrderID FROM (SELECT o.OrderID, o.TotalDue FROM Sales.Orders o) sub"
    )
    res_sub = PolicyEngine().authorize_and_apply(
        subquery_sql, space, runtime_context={"tenant_id": 12}
    )
    assert "o.TenantID = :qs_policy_0_0" in res_sub.sql


def test_union_branches_each_receive_policy() -> None:
    space = _make_orders_space()
    sql = "SELECT o.OrderID FROM Sales.Orders o UNION ALL SELECT o2.OrderID FROM Sales.Orders o2"
    res = PolicyEngine().authorize_and_apply(
        sql, space, runtime_context={"tenant_id": 44}
    )
    assert res.sql.count("TenantID") == 2
    assert len(res.parameters) == 4


def test_policy_injection_is_idempotent() -> None:
    space = _make_orders_space()
    engine = PolicyEngine()
    first = engine.authorize_and_apply(
        "SELECT o.OrderID FROM Sales.Orders o", space, runtime_context={"tenant_id": 1}
    )
    parsed = engine.parser.parse(first.sql)
    second = PolicyInjector().apply(parsed, space, runtime_context={"tenant_id": 1})
    assert second.expression.sql(dialect="tsql") == first.sql


# ==============================================================================
# Task 3: AST Rewriter & Final Authorization Safety Tests
# ==============================================================================


def test_original_ast_is_not_mutated() -> None:
    space = _make_orders_space()
    parsed = SQLParser().parse("SELECT o.OrderID FROM Sales.Orders o")
    before_sql = parsed.expression.sql(dialect="tsql")
    PolicyInjector().apply(parsed, space, runtime_context={"tenant_id": 3})
    after_sql = parsed.expression.sql(dialect="tsql")
    assert before_sql == after_sql


def test_execution_boundary_only_accepts_authorized_query() -> None:
    engine = FakeEngine()
    space = _make_orders_space()
    with pytest.raises(
        TypeError, match="execute_authorized_query requires an AuthorizedQuery"
    ):
        execute_authorized_query(engine, "SELECT * FROM Sales.Orders", space)  # type: ignore[arg-type]


def test_not_eq_operator_alias_support() -> None:
    rf = RequiredFilter(column="Status", operator="NOT_EQ", value="Cancelled")
    assert rf.operator is FilterOperator.NE
