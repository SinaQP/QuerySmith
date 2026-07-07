"""SQL Server schema introspection."""

from sqlalchemy import Engine, text

from querysmith.models import Column, ForeignKey, Table


def introspect_schema(engine: Engine, schema: str = "dbo") -> list[Table]:
    """Read table, column, primary key, and foreign key metadata for a schema."""

    tables_by_id: dict[int, Table] = {}

    with engine.connect() as connection:
        table_rows = connection.execute(
            text(
                """
                SELECT
                    t.object_id,
                    t.name AS table_name,
                    s.name AS schema_name
                FROM sys.tables AS t
                INNER JOIN sys.schemas AS s
                    ON s.schema_id = t.schema_id
                WHERE s.name = :schema
                ORDER BY t.name
                """
            ),
            {"schema": schema},
        ).mappings()

        for row in table_rows:
            tables_by_id[row["object_id"]] = Table(
                schema_name=row["schema_name"],
                name=row["table_name"],
            )

        if not tables_by_id:
            return []

        column_rows = connection.execute(
            text(
                """
                SELECT
                    t.object_id,
                    c.name AS column_name,
                    ty.name AS data_type,
                    c.is_nullable,
                    CASE WHEN pk.column_id IS NULL THEN 0 ELSE 1 END AS is_primary_key
                FROM sys.tables AS t
                INNER JOIN sys.schemas AS s
                    ON s.schema_id = t.schema_id
                INNER JOIN sys.columns AS c
                    ON c.object_id = t.object_id
                INNER JOIN sys.types AS ty
                    ON ty.user_type_id = c.user_type_id
                LEFT JOIN (
                    SELECT
                        ic.object_id,
                        ic.column_id
                    FROM sys.indexes AS i
                    INNER JOIN sys.index_columns AS ic
                        ON ic.object_id = i.object_id
                        AND ic.index_id = i.index_id
                    WHERE i.is_primary_key = 1
                ) AS pk
                    ON pk.object_id = c.object_id
                    AND pk.column_id = c.column_id
                WHERE s.name = :schema
                ORDER BY t.name, c.column_id
                """
            ),
            {"schema": schema},
        ).mappings()

        for row in column_rows:
            table = tables_by_id[row["object_id"]]
            table.columns.append(
                Column(
                    name=row["column_name"],
                    data_type=row["data_type"],
                    is_nullable=bool(row["is_nullable"]),
                    is_primary_key=bool(row["is_primary_key"]),
                )
            )

        foreign_key_rows = connection.execute(
            text(
                """
                SELECT
                    parent_table.object_id,
                    parent_column.name AS column_name,
                    referenced_table.name AS referenced_table,
                    referenced_column.name AS referenced_column
                FROM sys.foreign_keys AS fk
                INNER JOIN sys.foreign_key_columns AS fkc
                    ON fkc.constraint_object_id = fk.object_id
                INNER JOIN sys.tables AS parent_table
                    ON parent_table.object_id = fkc.parent_object_id
                INNER JOIN sys.schemas AS parent_schema
                    ON parent_schema.schema_id = parent_table.schema_id
                INNER JOIN sys.columns AS parent_column
                    ON parent_column.object_id = fkc.parent_object_id
                    AND parent_column.column_id = fkc.parent_column_id
                INNER JOIN sys.tables AS referenced_table
                    ON referenced_table.object_id = fkc.referenced_object_id
                INNER JOIN sys.columns AS referenced_column
                    ON referenced_column.object_id = fkc.referenced_object_id
                    AND referenced_column.column_id = fkc.referenced_column_id
                WHERE parent_schema.name = :schema
                ORDER BY parent_table.name, fk.name, fkc.constraint_column_id
                """
            ),
            {"schema": schema},
        ).mappings()

        for row in foreign_key_rows:
            table = tables_by_id[row["object_id"]]
            table.foreign_keys.append(
                ForeignKey(
                    column=row["column_name"],
                    referenced_table=row["referenced_table"],
                    referenced_column=row["referenced_column"],
                )
            )

    return list(tables_by_id.values())
