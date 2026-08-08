"""Unit and security tests for Phase 5 & 6 (Access Profiles, Result Sanitizer, Execution Safety, Required Filters)."""

from __future__ import annotations

import pytest

from querysmith import (
    AccessProfileResolver,
    CatalogResolver,
    ColumnAccess,
    ColumnAccessLevel,
    ColumnSpec,
    ExecutionPolicy,
    MaskingPolicy,
    MissingAccessProfileError,
    MissingRuntimeContextError,
    ProfiledQuerySpace,
    RequiredFilter,
    ResultAccess,
    ResultSanitizer,
    SanitizedResult,
    TableAccess,
    TableRef,
    TableSpec,
    TooManyJoinsError,
    UnknownAccessProfileError,
    ask,
)
from querysmith.catalog import CatalogColumn, CatalogSnapshot, CatalogTable
from querysmith.exceptions import (
    SubqueryNotAllowedError,
)
from querysmith.llm import LLMClient
from querysmith.models import QuerySpace, ResolvedQuerySpace
from querysmith.policy import PolicyEngine


class FakeLLMClient(LLMClient):
    def __init__(self, sql_response: str) -> None:
        self.sql_response = sql_response

    def complete(self, prompt: str) -> str:
        return self.sql_response


class FakeIntrospector:
    def __init__(self, snapshot: CatalogSnapshot) -> None:
        self.snapshot = snapshot

    def inspect_tables(self, refs: tuple[TableRef, ...]) -> CatalogSnapshot:
        return self.snapshot


def _make_resolved_space_with_profiles() -> ResolvedQuerySpace:
    tables = [
        TableSpec(
            ref=TableRef("Sales", "Orders"),
            alias="orders",
            columns=[
                ColumnSpec(
                    "OrderID",
                    "int",
                    nullable=False,
                    primary_key=True,
                    profiles={
                        "public": ColumnAccess.allow(),
                        "analyst": ColumnAccess.allow(),
                        "internal": ColumnAccess.allow(),
                    },
                ),
                ColumnSpec(
                    "TotalAmount",
                    "decimal",
                    nullable=False,
                    profiles={
                        "public": ColumnAccess.deny(),
                        "analyst": ColumnAccess(
                            selectable=False,
                            filterable=True,
                            sortable=False,
                            groupable=False,
                            aggregatable=False,
                            result_access=ResultAccess.HIDDEN,
                        ),
                        "internal": ColumnAccess.allow(),
                    },
                ),
                ColumnSpec(
                    "NationalIDNumber",
                    "nvarchar",
                    nullable=True,
                    profiles={
                        "public": ColumnAccess.deny(),
                        "analyst": ColumnAccess.deny(),
                        "internal": ColumnAccess(
                            selectable=True,
                            filterable=True,
                            sortable=False,
                            groupable=False,
                            aggregatable=False,
                            result_access=ResultAccess.MASKED,
                            masking=MaskingPolicy.partial(
                                visible_prefix=0, visible_suffix=4
                            ),
                        ),
                    },
                ),
                ColumnSpec(
                    "TenantID",
                    "int",
                    nullable=False,
                    access=ColumnAccessLevel.POLICY_ONLY,
                ),
            ],
            required_filters=[
                RequiredFilter(column="TenantID", value_from_context="tenant_id")
            ],
            profiles={
                "public": TableAccess(available=True),
                "analyst": TableAccess(available=True),
                "internal": TableAccess(available=True),
            },
        ),
    ]

    snapshot = CatalogSnapshot(
        requested_refs=(TableRef("Sales", "Orders"),),
        tables=[
            CatalogTable(
                TableRef("Sales", "Orders"),
                [
                    CatalogColumn("OrderID", "int", nullable=False, primary_key=True),
                    CatalogColumn("TotalAmount", "decimal", nullable=False),
                    CatalogColumn("NationalIDNumber", "nvarchar", nullable=True),
                    CatalogColumn("TenantID", "int", nullable=False),
                ],
            ),
        ],
    )

    space = QuerySpace(
        tables=tables,
        execution_policy=ExecutionPolicy(
            max_rows=100,
            max_joins=2,
            allow_execution=True,
            allow_subqueries=True,
            allow_ctes=True,
            allow_cross_join=False,
            allow_select_star=False,
        ),
    )
    return CatalogResolver(FakeIntrospector(snapshot)).resolve(space)


def test_access_profile_resolution_valid() -> None:
    resolved = _make_resolved_space_with_profiles()
    resolver = AccessProfileResolver()

    profiled = resolver.resolve(resolved, "analyst")
    assert isinstance(profiled, ProfiledQuerySpace)
    assert profiled.access_profile.name == "analyst"

    total_access = profiled.get_column_access(
        TableRef("Sales", "Orders"), "TotalAmount"
    )
    assert total_access is not None
    assert total_access.selectable is False
    assert total_access.filterable is True
    assert total_access.result_access == ResultAccess.HIDDEN


def test_access_profile_resolution_missing_raises() -> None:
    resolved = _make_resolved_space_with_profiles()
    resolver = AccessProfileResolver()

    with pytest.raises(MissingAccessProfileError):
        resolver.resolve(resolved, None)


def test_access_profile_resolution_unknown_raises() -> None:
    resolved = _make_resolved_space_with_profiles()
    resolver = AccessProfileResolver()

    with pytest.raises(UnknownAccessProfileError):
        resolver.resolve(resolved, "super_admin")


def test_context_builder_hides_denied_columns_for_active_profile() -> None:
    resolved = _make_resolved_space_with_profiles()
    resolver = AccessProfileResolver()
    profiled = resolver.resolve(resolved, "public")

    from querysmith.context import ContextBuilder

    context = ContextBuilder().build(profiled)

    assert "OrderID" in context
    assert "TotalAmount" not in context
    assert "NationalIDNumber" not in context
    assert "TenantID" not in context


def test_authorization_enforces_profile_capabilities() -> None:
    resolved = _make_resolved_space_with_profiles()
    resolver = AccessProfileResolver()
    profiled_analyst = resolver.resolve(resolved, "analyst")
    engine = PolicyEngine()

    # TotalAmount is filterable but NOT selectable under analyst
    sql_valid = "SELECT [OrderID] FROM [Sales].[Orders] WHERE [TotalAmount] > 100"
    authorized = engine.authorize_and_apply(
        sql_valid, profiled_analyst, runtime_context={"tenant_id": 42}
    )
    assert authorized.is_authorized
    assert ":qs_policy_" in authorized.sql
    assert authorized.parameters["qs_policy_0_0"] == 42

    sql_invalid_select = "SELECT [TotalAmount] FROM [Sales].[Orders]"
    from querysmith.authorization import ColumnOperationNotAllowedError

    with pytest.raises(ColumnOperationNotAllowedError):
        engine.authorize_and_apply(
            sql_invalid_select, profiled_analyst, runtime_context={"tenant_id": 42}
        )


def test_result_sanitizer_masking_and_hidden_removal() -> None:
    resolved = _make_resolved_space_with_profiles()
    resolver = AccessProfileResolver()
    profiled_internal = resolver.resolve(resolved, "internal")

    engine = PolicyEngine()
    sql = "SELECT [OrderID], [NationalIDNumber] FROM [Sales].[Orders]"
    authorized = engine.authorize_and_apply(
        sql, profiled_internal, runtime_context={"tenant_id": 10}
    )

    raw_db_rows = [
        {"OrderID": 1, "NationalIDNumber": "123456789"},
        {"OrderID": 2, "NationalIDNumber": "987654321"},
    ]

    sanitizer = ResultSanitizer()
    sanitized = sanitizer.sanitize(authorized, raw_db_rows, profiled_internal)

    assert isinstance(sanitized, SanitizedResult)
    assert sanitized.columns == ("OrderID", "NationalIDNumber")
    assert len(sanitized.rows) == 2
    assert sanitized.rows[0]["OrderID"] == 1
    assert sanitized.rows[0]["NationalIDNumber"] == "*****6789"
    assert sanitized.rows[1]["NationalIDNumber"] == "*****4321"


def test_required_filter_missing_runtime_context_raises() -> None:
    resolved = _make_resolved_space_with_profiles()
    resolver = AccessProfileResolver()
    profiled = resolver.resolve(resolved, "internal")

    engine = PolicyEngine()
    sql = "SELECT [OrderID] FROM [Sales].[Orders]"

    with pytest.raises(MissingRuntimeContextError):
        engine.authorize_and_apply(sql, profiled, runtime_context={})


def test_shape_checks_max_joins() -> None:
    snapshot = CatalogSnapshot(
        requested_refs=(
            TableRef("dbo", "A"),
            TableRef("dbo", "B"),
            TableRef("dbo", "C"),
        ),
        tables=[
            CatalogTable(
                TableRef("dbo", "A"), [CatalogColumn("id", "int", nullable=False)]
            ),
            CatalogTable(
                TableRef("dbo", "B"), [CatalogColumn("id", "int", nullable=False)]
            ),
            CatalogTable(
                TableRef("dbo", "C"), [CatalogColumn("id", "int", nullable=False)]
            ),
        ],
    )
    space = QuerySpace(
        tables=[
            TableSpec(ref=TableRef("dbo", "A"), columns=[ColumnSpec("id")]),
            TableSpec(ref=TableRef("dbo", "B"), columns=[ColumnSpec("id")]),
            TableSpec(ref=TableRef("dbo", "C"), columns=[ColumnSpec("id")]),
        ],
        execution_policy=ExecutionPolicy(max_joins=1),
    )
    resolved = CatalogResolver(FakeIntrospector(snapshot)).resolve(space)

    engine = PolicyEngine()
    sql = "SELECT [A].[id] FROM [dbo].[A] JOIN [dbo].[B] ON [A].[id] = [B].[id] JOIN [dbo].[C] ON [B].[id] = [C].[id]"

    with pytest.raises(TooManyJoinsError):
        engine.authorize_and_apply(sql, resolved)


def test_shape_checks_subqueries_disabled() -> None:
    snapshot = CatalogSnapshot(
        requested_refs=(TableRef("dbo", "A"),),
        tables=[
            CatalogTable(
                TableRef("dbo", "A"), [CatalogColumn("id", "int", nullable=False)]
            )
        ],
    )

    space = QuerySpace(
        tables=[TableSpec(ref=TableRef("dbo", "A"), columns=[ColumnSpec("id")])],
        execution_policy=ExecutionPolicy(allow_subqueries=False),
    )
    resolved = CatalogResolver(FakeIntrospector(snapshot)).resolve(space)

    engine = PolicyEngine()
    sql = "SELECT [id] FROM (SELECT [id] FROM [dbo].[A]) AS sub"

    with pytest.raises(SubqueryNotAllowedError):
        engine.authorize_and_apply(sql, resolved)


def test_pipeline_ask_end_to_end() -> None:
    resolved = _make_resolved_space_with_profiles()
    client = FakeLLMClient("SELECT [OrderID], [NationalIDNumber] FROM [Sales].[Orders]")

    sql = ask(
        question="Show my orders",
        query_space=resolved,
        access_profile="internal",
        runtime_context={"tenant_id": 99},
        client=client,
    )
    assert "SELECT" in sql
    assert "TenantID" in sql
