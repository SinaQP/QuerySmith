"""Bounded, parameterized SQL Server catalog introspection."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from querysmith.catalog import CatalogColumn, CatalogSnapshot, CatalogTable
from querysmith.models import (
    CatalogResolutionError,
    Column,
    DefaultColumnPolicy,
    ExecutionPolicy,
    ForeignKey,
    QuerySpace,
    QuerySpaceValidationError,
    RelationshipSpec,
    ResolvedQuerySpace,
    Table,
    TableRef,
    TableSpec,
)

_MAX_TABLES_PER_BATCH = 500
_P = ParamSpec("_P")
_R = TypeVar("_R")


def _catalog_operation(function: Callable[_P, _R]) -> Callable[_P, _R]:
    @wraps(function)
    def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        try:
            return function(*args, **kwargs)
        except SQLAlchemyError as error:
            raise CatalogResolutionError(
                "SQL Server catalog introspection failed."
            ) from error

    return wrapped


class SQLServerIntrospector:
    """Read metadata for exact table identities in a bounded query count."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @_catalog_operation
    def list_tables(self, schema: str) -> tuple[TableRef, ...]:
        """List physical tables for the compatibility schema adapter."""

        TableRef(schema, "__querysmith_validation__")
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT s.name AS schema_name, t.name AS table_name
                    FROM sys.tables AS t
                    INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
                    WHERE s.name = :schema
                    ORDER BY t.name
                    """
                ),
                {"schema": schema},
            ).mappings()
            return tuple(
                TableRef(row["schema_name"], row["table_name"]) for row in rows
            )

    @_catalog_operation
    def inspect_tables(self, table_refs: Iterable[TableRef]) -> CatalogSnapshot:
        """Inspect only requested fully-qualified tables using three catalog queries."""

        refs = _validated_refs(table_refs)
        table_predicate, parameters = _pair_predicate("s.name", "t.name", refs, "t")
        parent_predicate, parent_params = _pair_predicate(
            "parent_schema.name", "parent_table.name", refs, "p"
        )
        target_predicate, target_params = _pair_predicate(
            "referenced_schema.name", "referenced_table.name", refs, "r"
        )
        with self.engine.connect() as connection:
            table_rows = list(
                connection.execute(
                    text(
                        f"""
                        SELECT t.object_id, s.name AS schema_name, t.name AS table_name
                        FROM sys.tables AS t
                        INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
                        WHERE {table_predicate}
                        ORDER BY s.name, t.name
                        """
                    ),
                    parameters,
                ).mappings()
            )
            column_rows = list(
                connection.execute(
                    text(
                        f"""
                        SELECT t.object_id, c.name AS column_name,
                               ty.name AS data_type, c.max_length,
                               c.precision, c.scale, c.is_nullable,
                               CASE WHEN pk.column_id IS NULL THEN 0 ELSE 1 END
                                   AS is_primary_key
                        FROM sys.tables AS t
                        INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
                        INNER JOIN sys.columns AS c ON c.object_id = t.object_id
                        INNER JOIN sys.types AS ty
                            ON ty.system_type_id = c.system_type_id
                           AND ty.user_type_id = ty.system_type_id
                        LEFT JOIN (
                            SELECT ic.object_id, ic.column_id
                            FROM sys.indexes AS i
                            INNER JOIN sys.index_columns AS ic
                                ON ic.object_id = i.object_id
                               AND ic.index_id = i.index_id
                            WHERE i.is_primary_key = 1
                        ) AS pk ON pk.object_id = c.object_id
                               AND pk.column_id = c.column_id
                        WHERE {table_predicate}
                        ORDER BY s.name, t.name, c.column_id
                        """
                    ),
                    parameters,
                ).mappings()
            )
            relationship_rows = list(
                connection.execute(
                    text(
                        f"""
                        SELECT parent_schema.name AS source_schema,
                               parent_table.name AS source_table,
                               parent_column.name AS source_column,
                               referenced_schema.name AS target_schema,
                               referenced_table.name AS target_table,
                               referenced_column.name AS target_column
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
                        INNER JOIN sys.schemas AS referenced_schema
                            ON referenced_schema.schema_id = referenced_table.schema_id
                        INNER JOIN sys.columns AS referenced_column
                            ON referenced_column.object_id = fkc.referenced_object_id
                           AND referenced_column.column_id = fkc.referenced_column_id
                        WHERE ({parent_predicate}) AND ({target_predicate})
                        ORDER BY parent_schema.name, parent_table.name,
                                 fk.name, fkc.constraint_column_id
                        """
                    ),
                    {**parent_params, **target_params},
                ).mappings()
            )
        return _snapshot(refs, table_rows, column_rows, relationship_rows)


def inspect_tables(engine: Engine, table_refs: Iterable[TableRef]) -> CatalogSnapshot:
    """Typed convenience API for exact-table catalog introspection."""

    return SQLServerIntrospector(engine).inspect_tables(table_refs)


def introspect_schema(engine: Engine, schema: str = "dbo") -> list[Table]:
    """Compatibility adapter returning the original mutable schema models."""

    introspector = SQLServerIntrospector(engine)
    refs = introspector.list_tables(schema)
    if not refs:
        return []
    snapshot = introspector.inspect_tables(refs)
    tables: dict[TableRef, Table] = {}
    for catalog_table in snapshot.tables:
        tables[catalog_table.ref] = Table(
            schema_name=catalog_table.ref.schema,
            name=catalog_table.ref.table,
            columns=[
                Column(
                    column.name,
                    column.data_type,
                    column.nullable,
                    column.primary_key,
                )
                for column in catalog_table.columns
            ],
        )
    for relationship in snapshot.relationships:
        tables[relationship.source_table].foreign_keys.append(
            ForeignKey(
                relationship.source_column,
                relationship.target_table.full_name,
                relationship.target_column,
            )
        )
    return [tables[ref] for ref in refs]


def introspect_query_space(
    engine: Engine,
    *,
    schema: str | None = None,
    table_refs: Iterable[TableRef] | None = None,
    execution_policy: ExecutionPolicy | None = None,
) -> ResolvedQuerySpace:
    """Resolve a full legacy schema or exact selected table identities."""

    if (schema is None) == (table_refs is None):
        raise QuerySpaceValidationError(
            "Provide exactly one of schema or table_refs for introspection."
        )
    introspector = SQLServerIntrospector(engine)
    refs = (
        introspector.list_tables(schema or "")
        if schema is not None
        else tuple(table_refs or ())
    )
    refs = _validated_refs(refs)
    from querysmith.resolver import CatalogResolver

    developer_space = QuerySpace(
        tables=[TableSpec(ref) for ref in refs],
        execution_policy=execution_policy
        or ExecutionPolicy(allow_unlisted_joins=schema is not None),
        default_column_policy=DefaultColumnPolicy.ALLOW,
    )
    return CatalogResolver(introspector).resolve(developer_space)


def _validated_refs(table_refs: Iterable[TableRef]) -> tuple[TableRef, ...]:
    refs = tuple(table_refs)
    if not refs:
        raise QuerySpaceValidationError(
            "table_refs must contain at least one TableRef."
        )
    if any(not isinstance(ref, TableRef) for ref in refs):
        raise QuerySpaceValidationError(
            "table_refs must contain only TableRef instances."
        )
    if len(set(refs)) != len(refs):
        raise QuerySpaceValidationError("table_refs contains a duplicate table.")
    if len(refs) > _MAX_TABLES_PER_BATCH:
        raise QuerySpaceValidationError(
            f"table_refs cannot contain more than {_MAX_TABLES_PER_BATCH} tables."
        )
    return refs


def _pair_predicate(
    schema_expression: str,
    table_expression: str,
    refs: tuple[TableRef, ...],
    prefix: str,
) -> tuple[str, dict[str, str]]:
    clauses: list[str] = []
    parameters: dict[str, str] = {}
    for index, ref in enumerate(refs):
        schema_key = f"{prefix}_schema_{index}"
        table_key = f"{prefix}_table_{index}"
        clauses.append(
            f"({schema_expression} = :{schema_key} AND "
            f"{table_expression} = :{table_key})"
        )
        parameters[schema_key] = ref.schema
        parameters[table_key] = ref.table
    return " OR ".join(clauses), parameters


def _snapshot(
    refs: tuple[TableRef, ...],
    table_rows: Iterable[Any],
    column_rows: Iterable[Any],
    relationship_rows: Iterable[Any],
) -> CatalogSnapshot:
    selected = set(refs)
    columns_by_id: dict[int, list[CatalogColumn]] = {}
    for row in column_rows:
        data_type = str(row["data_type"])
        raw_length = int(row["max_length"])
        length = _catalog_length(data_type, raw_length)
        columns_by_id.setdefault(int(row["object_id"]), []).append(
            CatalogColumn(
                name=str(row["column_name"]),
                data_type=data_type,
                nullable=bool(row["is_nullable"]),
                primary_key=bool(row["is_primary_key"]),
                length=length,
                precision=int(row["precision"]),
                scale=int(row["scale"]),
            )
        )
    tables: list[CatalogTable] = []
    for row in table_rows:
        ref = TableRef(str(row["schema_name"]), str(row["table_name"]))
        if ref in selected:
            tables.append(
                CatalogTable(ref, columns_by_id.get(int(row["object_id"]), ()))
            )
    relationships: list[RelationshipSpec] = []
    for row in relationship_rows:
        relationship = RelationshipSpec(
            TableRef(str(row["source_schema"]), str(row["source_table"])),
            str(row["source_column"]),
            TableRef(str(row["target_schema"]), str(row["target_table"])),
            str(row["target_column"]),
        )
        if (
            relationship.source_table in selected
            and relationship.target_table in selected
        ):
            relationships.append(relationship)
    return CatalogSnapshot(refs, tables, relationships)


def _catalog_length(data_type: str, max_length: int) -> int | None:
    base = data_type.casefold()
    if base not in {"char", "varchar", "nchar", "nvarchar", "binary", "varbinary"}:
        return None
    if max_length == -1:
        return -1
    return max_length // 2 if base in {"nchar", "nvarchar"} else max_length
