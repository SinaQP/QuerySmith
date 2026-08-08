"""Tests for QuerySpace domain validation and lookup behavior."""

import pytest

from querysmith import (
    ColumnSpec,
    ExecutionPolicy,
    QuerySpace,
    QuerySpaceLookupError,
    QuerySpaceValidationError,
    RelationshipSpec,
    TableRef,
    TableSpec,
)
from querysmith.models import Column, ForeignKey, Table


def _table(schema: str, name: str, *columns: str) -> TableSpec:
    return TableSpec(
        ref=TableRef(schema, name),
        columns=tuple(ColumnSpec(column, "int", False) for column in columns),
    )


def test_table_ref_uses_fully_qualified_case_insensitive_identity() -> None:
    person = TableRef("Person", "Address")

    assert person != TableRef("Sales", "Address")
    assert person == TableRef("person", "address")
    assert hash(person) == hash(TableRef("PERSON", "ADDRESS"))
    assert person.full_name == "Person.Address"


@pytest.mark.parametrize(
    ("schema", "table"),
    [("", "Users"), ("   ", "Users"), ("dbo", ""), ("dbo", "\t")],
)
def test_table_ref_rejects_empty_identifiers(schema: str, table: str) -> None:
    with pytest.raises(QuerySpaceValidationError):
        TableRef(schema, table)


def test_query_space_accepts_multiple_schemas_and_same_short_name() -> None:
    person_address = _table("Person", "Address", "Id")
    sales_address = _table("Sales", "Address", "Id")
    query_space = QuerySpace([person_address, sales_address])

    assert query_space.get_table(TableRef("Person", "Address")) is person_address
    assert query_space.get_table(TableRef("sales", "address")) is sales_address


def test_query_space_rejects_empty_and_duplicate_tables() -> None:
    with pytest.raises(QuerySpaceValidationError, match="at least one table"):
        QuerySpace([])

    users = _table("dbo", "Users", "Id")
    with pytest.raises(QuerySpaceValidationError, match="Duplicate table"):
        QuerySpace([users, _table("DBO", "USERS", "Id")])


def test_table_spec_rejects_duplicate_columns() -> None:
    with pytest.raises(QuerySpaceValidationError, match="Duplicate column"):
        TableSpec(
            TableRef("dbo", "Users"),
            [ColumnSpec("Id", "int", False), ColumnSpec("ID", "int", False)],
        )


def test_query_space_lookup_reports_missing_table() -> None:
    query_space = QuerySpace([_table("dbo", "Users", "Id")])

    with pytest.raises(QuerySpaceLookupError, match="sales.Users"):
        query_space.get_table(TableRef("sales", "Users"))


@pytest.mark.parametrize(
    "relationship",
    [
        RelationshipSpec(
            TableRef("missing", "Source"),
            "Id",
            TableRef("dbo", "Users"),
            "Id",
        ),
        RelationshipSpec(
            TableRef("dbo", "Users"),
            "Id",
            TableRef("missing", "Target"),
            "Id",
        ),
    ],
)
def test_query_space_rejects_relationship_tables_outside_space(
    relationship: RelationshipSpec,
) -> None:
    users = _table("dbo", "Users", "Id")
    orders = _table("dbo", "Orders", "Id", "UserId")

    with pytest.raises(QuerySpaceValidationError):
        QuerySpace([users, orders], [relationship])


def test_developer_query_space_allows_partial_relationship_columns() -> None:
    users = _table("dbo", "Users", "Id")
    orders = _table("dbo", "Orders", "Id")
    relationship = RelationshipSpec(orders.ref, "UserId", users.ref, "Id")

    assert QuerySpace([users, orders], [relationship]).relationships == (relationship,)


def test_query_space_accepts_relationship_and_rejects_duplicate() -> None:
    users = _table("dbo", "Users", "Id")
    orders = _table("dbo", "Orders", "Id", "UserId")
    relationship = RelationshipSpec(
        orders.ref,
        "UserId",
        users.ref,
        "Id",
    )

    assert QuerySpace([users, orders], [relationship]).relationships == (relationship,)
    with pytest.raises(QuerySpaceValidationError, match="Duplicate relationship"):
        QuerySpace([users, orders], [relationship, relationship])


def test_legacy_conversion_filters_relationship_outside_query_space() -> None:
    orders = Table(
        schema_name="Sales",
        name="Orders",
        columns=[Column("CustomerId", "int", False)],
        foreign_keys=[
            ForeignKey("CustomerId", "CRM.Customers", "Id"),
        ],
    )

    query_space = QuerySpace.from_legacy_tables([orders])

    assert query_space.relationships == ()


def test_execution_policy_rejects_invalid_limits() -> None:
    with pytest.raises(QuerySpaceValidationError, match="max_rows"):
        ExecutionPolicy(max_rows=0)
