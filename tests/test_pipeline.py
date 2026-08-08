"""Tests for QuerySmith pipeline helpers."""

from __future__ import annotations

from typing import Self

import pytest

from querysmith import AuthorizedQuery, MissingQuerySpaceError, ask
from querysmith.catalog import CatalogColumn, CatalogSnapshot, CatalogTable
from querysmith.guard import UnsafeQueryError
from querysmith.models import (
    Column,
    ColumnAccess,
    ColumnSpec,
    ExecutionPolicy,
    MandatoryFilterPolicy,
    QuerySpace,
    QuerySpaceValidationError,
    RelationshipSpec,
    ResolvedQuerySpace,
    Table,
    TableNotFoundError,
    TableRef,
    TableSpec,
)
from querysmith.pipeline import (
    authorize_query_in_space,
    execute_authorized_query,
    execute_select,
    generate_query,
    generate_query_in_space,
)
from querysmith.resolver import CatalogResolver


class FakeClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


class FakeEngine:
    def __init__(self) -> None:
        self.connect_calls = 0
        self.sql = ""
        self.parameters: dict[str, object] = {}

    def connect(self) -> FakeConnection:
        self.connect_calls += 1
        return FakeConnection(self)


class FakeConnection:
    def __init__(self, engine: FakeEngine) -> None:
        self.engine = engine

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(
        self, statement: object, parameters: dict[str, object] | None = None
    ) -> FakeResult:
        self.engine.sql = str(statement)
        self.engine.parameters = parameters or {}
        return FakeResult()


class FakeResult:
    def mappings(self) -> list[dict[str, object]]:
        return [{"Id": 1, "Name": "Alice"}]


class FakeCatalogIntrospector:
    def __init__(self, *, missing: bool = False) -> None:
        self.missing = missing
        self.calls = 0

    def inspect_tables(self, table_refs: tuple[TableRef, ...]) -> CatalogSnapshot:
        self.calls += 1
        tables = (
            ()
            if self.missing
            else (
                CatalogTable(
                    TableRef("Sales", "Customer"),
                    (CatalogColumn("CustomerId", "int", False),),
                ),
            )
        )
        return CatalogSnapshot(table_refs, tables)


def _space(*, policy: ExecutionPolicy | None = None) -> ResolvedQuerySpace:
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
        [
            RelationshipSpec(
                orders.ref,
                "CustomerId",
                customer.ref,
                "CustomerId",
            )
        ],
        policy or ExecutionPolicy(),
    )


def _mandatory_policy_space() -> ResolvedQuerySpace:
    customer = TableRef("Sales", "Customer")
    return ResolvedQuerySpace(
        [
            TableSpec(
                customer,
                [
                    ColumnSpec("CustomerId", "int", False),
                    ColumnSpec(
                        "IsDeleted",
                        "bit",
                        False,
                        access=ColumnAccess.POLICY_ONLY,
                    ),
                ],
            )
        ],
        execution_policy=ExecutionPolicy(
            max_rows=7,
            mandatory_filters=(
                MandatoryFilterPolicy(customer, "IsDeleted", "=", False),
            ),
        ),
    )


def test_generate_query_returns_sql_from_fake_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "querysmith.pipeline.introspect_schema",
        lambda engine, schema: [
            Table(
                schema_name=schema,
                name="Users",
                columns=[Column("Id", "int", False, True)],
            )
        ],
    )
    client = FakeClient("SELECT Id FROM dbo.Users")

    assert generate_query("show users", FakeEngine(), client) == (
        "SELECT TOP 100 Id FROM dbo.Users"
    )


def test_generate_query_passes_serialized_schema_to_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "querysmith.pipeline.introspect_schema",
        lambda engine, schema: [
            Table(
                schema_name=schema,
                name="Users",
                columns=[Column("Id", "int", False, True)],
            )
        ],
    )
    client = FakeClient("SELECT Id FROM dbo.Users")

    generate_query("show users", FakeEngine(), client)

    assert "dbo.Users" in client.prompts[0]
    assert "- Id int [PK]" in client.prompts[0]


def test_generate_query_does_not_execute_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = FakeEngine()
    monkeypatch.setattr(
        "querysmith.pipeline.introspect_schema",
        lambda engine, schema: [],
    )
    client = FakeClient("SELECT 1")

    generate_query("show one", engine, client)

    assert engine.sql == ""


def test_generate_query_does_not_instantiate_openai_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "querysmith.pipeline.introspect_schema",
        lambda engine, schema: [],
    )
    client = FakeClient("SELECT 1")

    assert generate_query("show one", FakeEngine(), client) == "SELECT 1"


def test_execute_select_without_query_space_fails_closed() -> None:
    engine = FakeEngine()

    with pytest.raises(MissingQuerySpaceError):
        execute_select(engine, "SELECT CustomerId FROM Sales.Customer")

    assert engine.connect_calls == 0


@pytest.mark.parametrize("max_rows", [0, -1, 1001, "10", True])
def test_execute_select_rejects_invalid_max_rows(max_rows: object) -> None:
    with pytest.raises(ValueError):
        execute_select(
            FakeEngine(),
            "SELECT CustomerId FROM Sales.Customer",
            max_rows=max_rows,
            query_space=_space(),
        )


def test_execute_select_wraps_safe_sql_and_returns_sanitized_result() -> None:
    engine = FakeEngine()
    space = _space()

    res = execute_select(
        engine, "SELECT CustomerId FROM Sales.Customer", max_rows=10, query_space=space
    )

    assert res.columns == ("CustomerId",)
    assert res.rows == ({"CustomerId": 1},)
    assert "SELECT TOP 10 CustomerId FROM Sales.Customer" in engine.sql


def test_generate_query_in_space_serializes_scope_and_guards_response() -> None:
    client = FakeClient(
        "SELECT c.CustomerId FROM Sales.Customer AS c "
        "JOIN Sales.Orders AS o ON o.CustomerId = c.CustomerId"
    )

    sql = generate_query_in_space("show customers with orders", _space(), client)

    assert "Sales.Customer" in client.prompts[0]
    assert "Sales.Orders" in client.prompts[0]
    assert "schema-qualified" in client.prompts[0]
    assert sql.startswith("SELECT TOP 100 c.CustomerId")


def test_generate_query_in_space_rejects_llm_table_outside_scope() -> None:
    with pytest.raises(UnsafeQueryError, match="outside the active QuerySpace"):
        generate_query_in_space(
            "show users",
            _space(),
            FakeClient("SELECT Id FROM dbo.Users"),
        )


def test_authorize_query_in_space_returns_final_immutable_artifact() -> None:
    authorized = authorize_query_in_space(
        "show customers",
        _mandatory_policy_space(),
        FakeClient("SELECT c.CustomerId FROM Sales.Customer c"),
    )

    assert isinstance(authorized, AuthorizedQuery)
    assert "TOP 7" in authorized.sql
    assert "c.IsDeleted = :qs_policy_0_0" in authorized.sql
    assert dict(authorized.parameters) == {"qs_policy_0_0": False}


def test_ask_executes_only_final_policy_sql_with_bound_parameters() -> None:
    engine = FakeEngine()

    rows = ask(
        "show customers",
        query_space=_mandatory_policy_space(),
        engine=engine,
        client=FakeClient("SELECT c.CustomerId FROM Sales.Customer c"),
        execute=True,
    )

    assert rows == [{"Id": 1, "Name": "Alice"}]
    assert "TOP 7" in engine.sql
    assert "c.IsDeleted = :qs_policy_0_0" in engine.sql
    assert engine.parameters == {"qs_policy_0_0": False}


def test_ask_authorization_failure_prevents_connection() -> None:
    engine = FakeEngine()

    with pytest.raises(UnsafeQueryError):
        ask(
            "show salaries",
            query_space=_mandatory_policy_space(),
            engine=engine,
            client=FakeClient("SELECT s.Salary FROM Finance.Salaries s"),
            execute=True,
        )

    assert engine.connect_calls == 0


def test_execution_boundary_rejects_raw_sql() -> None:
    with pytest.raises(TypeError, match="AuthorizedQuery"):
        execute_authorized_query(
            FakeEngine(),
            "SELECT CustomerId FROM Sales.Customer",  # type: ignore[arg-type]
            _space(),
        )


def test_legacy_ask_adapts_schema_to_query_space(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query_space = _space()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        QuerySpace,
        "from_schema",
        classmethod(
            lambda cls, schema, *, engine: (
                captured.update(schema=schema, engine=engine) or query_space
            )
        ),
    )

    result = ask(
        question="Show all customers",
        schema="Sales",
        engine=FakeEngine(),
        client=FakeClient("SELECT CustomerId FROM Sales.Customer"),
    )

    assert result == "SELECT TOP 100 CustomerId FROM Sales.Customer"
    assert captured["schema"] == "Sales"
    assert isinstance(captured["engine"], FakeEngine)


def test_new_ask_accepts_query_space_without_database_engine() -> None:
    result = ask(
        question="Show customers",
        query_space=_space(),
        client=FakeClient("SELECT CustomerId FROM Sales.Customer"),
    )

    assert result == "SELECT TOP 100 CustomerId FROM Sales.Customer"


@pytest.mark.parametrize(
    ("schema", "query_space"),
    [(None, None), ("Sales", _space())],
)
def test_ask_requires_exactly_one_scope(
    schema: str | None,
    query_space: QuerySpace | None,
) -> None:
    with pytest.raises(QuerySpaceValidationError, match="exactly one"):
        ask(
            question="Show customers",
            schema=schema,
            query_space=query_space,
            client=FakeClient("SELECT 1"),
        )


def test_execute_select_enforces_query_space_policy_and_scope() -> None:
    engine = FakeEngine()
    query_space = _space(policy=ExecutionPolicy(max_rows=5))

    execute_select(
        engine,
        "SELECT CustomerId FROM Sales.Customer",
        max_rows=20,
        query_space=query_space,
    )

    assert "SELECT TOP 5 CustomerId" in engine.sql
    with pytest.raises(UnsafeQueryError):
        execute_select(
            FakeEngine(),
            "SELECT Id FROM dbo.Users",
            query_space=query_space,
        )


def test_execute_select_respects_disabled_execution_policy() -> None:
    query_space = _space(policy=ExecutionPolicy(allow_execution=False))

    with pytest.raises(QuerySpaceValidationError, match="disabled"):
        execute_select(
            FakeEngine(),
            "SELECT CustomerId FROM Sales.Customer",
            query_space=query_space,
        )


def test_ask_resolves_developer_space_exactly_once_before_llm() -> None:
    introspector = FakeCatalogIntrospector()
    client = FakeClient("SELECT CustomerId FROM Sales.Customer")
    developer = QuerySpace(
        [TableSpec(TableRef("Sales", "Customer"), [ColumnSpec("CustomerId")])]
    )

    sql = ask(
        "show customers",
        query_space=developer,
        resolver=CatalogResolver(introspector),
        client=client,
    )

    assert sql == "SELECT TOP 100 CustomerId FROM Sales.Customer"
    assert introspector.calls == 1
    assert len(client.prompts) == 1


def test_resolution_failure_prevents_llm_call() -> None:
    introspector = FakeCatalogIntrospector(missing=True)
    client = FakeClient("SELECT CustomerId FROM Sales.Customer")
    engine = FakeEngine()
    developer = QuerySpace(
        [TableSpec(TableRef("Sales", "Customer"), [ColumnSpec("CustomerId")])]
    )

    with pytest.raises(TableNotFoundError):
        ask(
            "show customers",
            query_space=developer,
            resolver=CatalogResolver(introspector),
            client=client,
            engine=engine,
            execute=True,
        )

    assert introspector.calls == 1
    assert client.prompts == []
    assert engine.connect_calls == 0
