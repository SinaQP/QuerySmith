"""Schema data models for QuerySmith."""

from dataclasses import dataclass, field


@dataclass
class Column:
    """A SQL Server table column."""

    name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool = False
    description: str | None = None


@dataclass
class ForeignKey:
    """A SQL Server foreign key relationship."""

    column: str
    referenced_table: str
    referenced_column: str


@dataclass
class Table:
    """A SQL Server table with columns and foreign keys."""

    schema_name: str
    name: str
    columns: list[Column] = field(default_factory=list)
    foreign_keys: list[ForeignKey] = field(default_factory=list)
    description: str | None = None

    @property
    def full_name(self) -> str:
        """Return the schema-qualified table name."""

        return f"{self.schema_name}.{self.name}"
