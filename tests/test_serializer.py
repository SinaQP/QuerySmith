"""Tests for schema serialization."""

import pytest

from querysmith.models import (
    Column,
    ColumnSpec,
    ForeignKey,
    QuerySpace,
    RelationshipSpec,
    ResolvedQuerySpace,
    Table,
    TableRef,
    TableSpec,
)
from querysmith.serializer import serialize_query_space, serialize_schema


def test_serialize_schema_returns_empty_marker_for_no_tables() -> None:
    assert serialize_schema([]) == "Database schema: <empty>"


def test_serialize_schema_is_compact_and_deterministic() -> None:
    orders = Table(
        schema_name="dbo",
        name="Orders",
        columns=[
            Column(
                name="Id",
                data_type="int",
                is_nullable=False,
                is_primary_key=True,
            ),
            Column(
                name="CustomerId",
                data_type="int",
                is_nullable=False,
            ),
            Column(
                name="Notes",
                data_type="nvarchar",
                is_nullable=True,
            ),
        ],
        foreign_keys=[
            ForeignKey(
                column="CustomerId",
                referenced_table="Customers",
                referenced_column="Id",
            )
        ],
    )
    customers = Table(
        schema_name="dbo",
        name="Customers",
        columns=[
            Column(
                name="Id",
                data_type="int",
                is_nullable=False,
                is_primary_key=True,
            ),
            Column(
                name="Name",
                data_type="nvarchar",
                is_nullable=False,
            ),
        ],
    )

    assert (
        serialize_schema([orders, customers])
        == "Database schema:\ndbo.Customers\n- Id int [PK]\n- Name nvarchar\ndbo.Orders\n- Id int [PK]\n- CustomerId int [FK -> dbo.Customers.Id]\n- Notes nvarchar [nullable]\n\nRelationships:\n- dbo.Orders.CustomerId -> dbo.Customers.Id"
    )


def test_serialize_schema_marks_no_relationships() -> None:
    table = Table(
        schema_name="sales",
        name="Invoices",
        columns=[
            Column(
                name="InvoiceId",
                data_type="int",
                is_nullable=False,
                is_primary_key=True,
            )
        ],
    )

    assert (
        serialize_schema([table])
        == "Database schema:\nsales.Invoices\n- InvoiceId int [PK]\n\nRelationships: <none>"
    )


def test_serialize_query_space_uses_only_fully_qualified_selected_tables() -> None:
    person = TableSpec(
        TableRef("Person", "Person"),
        [ColumnSpec("BusinessEntityID", "int", False, primary_key=True)],
    )
    employee = TableSpec(
        TableRef("HumanResources", "Employee"),
        [ColumnSpec("BusinessEntityID", "int", False)],
    )
    activity = TableSpec(
        TableRef("Activity", "PersonActivity"),
        [ColumnSpec("PersonId", "int", False)],
    )
    customer = TableSpec(
        TableRef("Sales", "Customer"),
        [ColumnSpec("PersonId", "int", False)],
    )
    query_space = ResolvedQuerySpace(
        [person, employee, activity, customer],
        [
            RelationshipSpec(
                employee.ref,
                "BusinessEntityID",
                person.ref,
                "BusinessEntityID",
            ),
            RelationshipSpec(
                activity.ref,
                "PersonId",
                person.ref,
                "BusinessEntityID",
            ),
            RelationshipSpec(
                customer.ref,
                "PersonId",
                person.ref,
                "BusinessEntityID",
            ),
        ],
    )

    serialized = serialize_query_space(query_space)

    for full_name in (
        "Person.Person",
        "HumanResources.Employee",
        "Activity.PersonActivity",
        "Sales.Customer",
    ):
        assert full_name in serialized
    assert "dbo.Users" not in serialized


def test_serializer_requires_resolved_space_and_labels_aliases_as_semantic() -> None:
    developer = QuerySpace([TableSpec(TableRef("dbo", "Users"), [ColumnSpec("Id")])])
    with pytest.raises(TypeError, match="ResolvedQuerySpace"):
        serialize_query_space(developer)  # type: ignore[arg-type]

    resolved = ResolvedQuerySpace(
        [
            TableSpec(
                TableRef("dbo", "Users"),
                [ColumnSpec("Id", "int", False, alias="user_id")],
                alias="people",
            )
        ]
    )
    serialized = serialize_query_space(resolved)

    assert "semantic alias: people" in serialized
    assert "semantic alias: user_id" in serialized
    assert "physical column names" in serialized
