"""Tests for bounded exact-table SQL Server introspection."""

from __future__ import annotations

from typing import Any, Self

import pytest

from querysmith.introspector import inspect_tables, introspect_query_space
from querysmith.models import QuerySpaceValidationError, ResolvedQuerySpace, TableRef


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def mappings(self) -> FakeResult:
        return self

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.rows)


class FakeConnection:
    def __init__(self, engine: FakeEngine) -> None:
        self.engine = engine

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, statement: object, parameters: dict[str, str]) -> FakeResult:
        sql = str(statement)
        self.engine.calls.append((sql, parameters))
        if "FROM sys.foreign_keys" in sql:
            return FakeResult(
                [
                    {
                        "source_schema": "Sales",
                        "source_table": "Orders",
                        "source_column": "CustomerId",
                        "target_schema": "CRM",
                        "target_table": "Customer",
                        "target_column": "CustomerId",
                    }
                ]
            )
        if "INNER JOIN sys.columns AS c" in sql:
            return FakeResult(
                [
                    {
                        "object_id": 1,
                        "column_name": "OrderId",
                        "data_type": "int",
                        "max_length": 4,
                        "precision": 10,
                        "scale": 0,
                        "is_nullable": False,
                        "is_primary_key": True,
                    },
                    {
                        "object_id": 1,
                        "column_name": "CustomerId",
                        "data_type": "int",
                        "max_length": 4,
                        "precision": 10,
                        "scale": 0,
                        "is_nullable": False,
                        "is_primary_key": False,
                    },
                    {
                        "object_id": 2,
                        "column_name": "CustomerId",
                        "data_type": "int",
                        "max_length": 4,
                        "precision": 10,
                        "scale": 0,
                        "is_nullable": False,
                        "is_primary_key": True,
                    },
                ]
            )
        return FakeResult(
            [
                {"object_id": 1, "schema_name": "Sales", "table_name": "Orders"},
                {"object_id": 2, "schema_name": "CRM", "table_name": "Customer"},
            ]
        )


class FakeEngine:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def connect(self) -> FakeConnection:
        return FakeConnection(self)


def test_inspect_tables_uses_three_bounded_parameterized_queries() -> None:
    engine = FakeEngine()
    refs = [TableRef("Sales", "Orders"), TableRef("CRM", "Customer")]

    snapshot = inspect_tables(engine, refs)  # type: ignore[arg-type]

    assert len(engine.calls) == 3
    assert snapshot.requested_refs == tuple(refs)
    assert {table.ref for table in snapshot.tables} == set(refs)
    assert len(snapshot.relationships) == 1
    for sql, parameters in engine.calls:
        assert "Sales" not in sql and "Orders" not in sql
        assert parameters


def test_selected_introspection_returns_resolved_space_and_catalog_fk() -> None:
    engine = FakeEngine()

    space = introspect_query_space(
        engine,  # type: ignore[arg-type]
        table_refs=[TableRef("Sales", "Orders"), TableRef("CRM", "Customer")],
    )

    assert isinstance(space, ResolvedQuerySpace)
    assert len(space.relationships) == 1
    assert (
        space.get_table(TableRef("Sales", "Orders")).get_column("OrderId").length
        is None
    )


def test_selective_introspection_caps_batch_below_sql_server_parameter_limit() -> None:
    refs = [TableRef("dbo", f"Table{index}") for index in range(501)]

    with pytest.raises(QuerySpaceValidationError, match="500"):
        inspect_tables(FakeEngine(), refs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "refs",
    [[], [TableRef("dbo", "Users"), TableRef("DBO", "USERS")]],
)
def test_selective_introspection_rejects_empty_or_duplicate_refs(
    refs: list[TableRef],
) -> None:
    engine = FakeEngine()

    with pytest.raises(QuerySpaceValidationError):
        inspect_tables(engine, refs)  # type: ignore[arg-type]

    assert engine.calls == []
