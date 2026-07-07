"""Serialize schema metadata for prompt context."""

from querysmith.models import Column, ForeignKey, Table


def serialize_schema(tables: list[Table]) -> str:
    """Convert introspected tables into compact, deterministic text."""

    if not tables:
        return "Database schema: <empty>"

    sorted_tables = sorted(tables, key=lambda table: (table.schema_name, table.name))
    lines: list[str] = ["Database schema:"]
    relationships: list[str] = []

    for table in sorted_tables:
        lines.append(_qualified_table_name(table))

        foreign_keys_by_column = {
            foreign_key.column: foreign_key for foreign_key in table.foreign_keys
        }

        for column in table.columns:
            foreign_key = foreign_keys_by_column.get(column.name)
            lines.append(f"- {_serialize_column(column, table, foreign_key)}")

        for foreign_key in sorted(
            table.foreign_keys,
            key=lambda fk: (fk.column, fk.referenced_table, fk.referenced_column),
        ):
            relationships.append(
                "- "
                f"{_qualified_table_name(table)}.{foreign_key.column} -> "
                f"{_qualified_referenced_table(table, foreign_key)}."
                f"{foreign_key.referenced_column}"
            )

    if relationships:
        lines.append("")
        lines.append("Relationships:")
        lines.extend(sorted(relationships))
    else:
        lines.append("")
        lines.append("Relationships: <none>")

    return "\n".join(lines)


def _serialize_column(
    column: Column,
    table: Table,
    foreign_key: ForeignKey | None,
) -> str:
    markers: list[str] = []

    if column.is_primary_key:
        markers.append("PK")

    if column.is_nullable:
        markers.append("nullable")

    if foreign_key is not None:
        markers.append(
            "FK -> "
            f"{_qualified_referenced_table(table, foreign_key)}."
            f"{foreign_key.referenced_column}"
        )

    suffix = f" [{' | '.join(markers)}]" if markers else ""
    return f"{column.name} {column.data_type}{suffix}"


def _qualified_table_name(table: Table) -> str:
    return f"{table.schema_name}.{table.name}"


def _qualified_referenced_table(table: Table, foreign_key: ForeignKey) -> str:
    if "." in foreign_key.referenced_table:
        return foreign_key.referenced_table

    return f"{table.schema_name}.{foreign_key.referenced_table}"
