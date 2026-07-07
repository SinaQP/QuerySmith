"""Tests for schema serialization."""

from querysmith.models import Column, ForeignKey, Table
from querysmith.serializer import serialize_schema


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

    assert serialize_schema([orders, customers]) == "\n".join(
        [
            "Database schema:",
            "dbo.Customers",
            "- Id int [PK]",
            "- Name nvarchar",
            "dbo.Orders",
            "- Id int [PK]",
            "- CustomerId int [FK -> dbo.Customers.Id]",
            "- Notes nvarchar [nullable]",
            "",
            "Relationships:",
            "- dbo.Orders.CustomerId -> dbo.Customers.Id",
        ]
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

    assert serialize_schema([table]) == "\n".join(
        [
            "Database schema:",
            "sales.Invoices",
            "- InvoiceId int [PK]",
            "",
            "Relationships: <none>",
        ]
    )
