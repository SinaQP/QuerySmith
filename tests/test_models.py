"""Tests for QuerySmith schema data models."""

from querysmith.models import Column, ForeignKey, Table


def test_table_full_name_and_schema_fields() -> None:
    """A table exposes its schema-qualified name and stored metadata."""

    table = Table(
        schema_name="dbo",
        name="Orders",
        columns=[
            Column(name="OrderId", data_type="int", is_nullable=False),
            Column(name="UserId", data_type="int", is_nullable=False),
            Column(name="Notes", data_type="varchar(50)", is_nullable=True),
        ],
        foreign_keys=[
            ForeignKey(
                column="UserId",
                referenced_table="dbo.Users",
                referenced_column="UserId",
            )
        ],
    )

    assert table.full_name == "dbo.Orders"
    assert table.columns[0].is_primary_key is False
    assert table.columns[0].description is None
    assert table.columns[2].data_type == "varchar(50)"
    assert table.foreign_keys[0].column == "UserId"
    assert table.foreign_keys[0].referenced_table == "dbo.Users"
    assert table.foreign_keys[0].referenced_column == "UserId"
