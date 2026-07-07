"""Tests for QuerySmith pipeline helpers."""

from __future__ import annotations

import pytest

from querysmith.guard import UnsafeQueryError
from querysmith.models import Column, Table
from querysmith.pipeline import execute_select, generate_query


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

    def connect(self) -> FakeConnection:
        self.connect_calls += 1
        return FakeConnection(self)


class FakeConnection:
    def __init__(self, engine: FakeEngine) -> None:
        self.engine = engine

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, statement: object) -> FakeResult:
        self.engine.sql = str(statement)
        return FakeResult()


class FakeResult:
    def mappings(self) -> list[dict[str, object]]:
        return [{"Id": 1, "Name": "Alice"}]


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
        "SELECT Id FROM dbo.Users"
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


def test_execute_select_rejects_unsafe_sql() -> None:
    engine = FakeEngine()

    with pytest.raises(UnsafeQueryError):
        execute_select(engine, "DELETE FROM dbo.Users")

    assert engine.connect_calls == 0


@pytest.mark.parametrize("max_rows", [0, -1, 1001, "10", True])
def test_execute_select_rejects_invalid_max_rows(max_rows: object) -> None:
    with pytest.raises(ValueError):
        execute_select(FakeEngine(), "SELECT Id FROM dbo.Users", max_rows=max_rows)


def test_execute_select_validates_sql_before_execution() -> None:
    engine = FakeEngine()

    with pytest.raises(UnsafeQueryError):
        execute_select(engine, "SELECT Id FROM dbo.Users; DROP TABLE dbo.Users")

    assert engine.connect_calls == 0


def test_execute_select_wraps_safe_sql_and_returns_rows() -> None:
    engine = FakeEngine()

    rows = execute_select(engine, "SELECT Id, Name FROM dbo.Users", max_rows=10)

    assert rows == [{"Id": 1, "Name": "Alice"}]
    assert "SELECT TOP (10) *" in engine.sql
    assert "SELECT Id, Name FROM dbo.Users" in engine.sql
