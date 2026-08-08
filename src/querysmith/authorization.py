"""AST-based T-SQL parsing and QuerySpace authorization."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, cast

from sqlglot import exp, parse
from sqlglot.errors import ParseError
from sqlglot.optimizer.scope import Scope, traverse_scope

from querysmith.exceptions import (
    AuthorizationErrorCode,
    CTENotAllowedError,
    HiddenColumnExposureError,
    QueryShapeNotAllowedError,
    SQLAuthorizationError,
    SubqueryNotAllowedError,
    TooManyJoinsError,
    UnsupportedMaskedExpressionError,
)
from querysmith.exceptions import (
    FinalAuthorizationError as _FinalAuthorizationError,
)
from querysmith.exceptions import MandatoryPolicyError as _MandatoryPolicyError
from querysmith.exceptions import PolicyInjectionError as _PolicyInjectionError
from querysmith.models import (
    ColumnAccess,
    ColumnAccessLevel,
    ExecutionPolicy,
    JoinType,
    ProfiledQuerySpace,
    ProjectionColumn,
    RelationshipSpec,
    ResolvedColumn,
    ResolvedQuerySpace,
    ResultAccess,
    TableRef,
)

FinalAuthorizationError = _FinalAuthorizationError
MandatoryPolicyError = _MandatoryPolicyError
PolicyInjectionError = _PolicyInjectionError


class UnsafeQueryError(SQLAuthorizationError):
    """Compatibility base for rejected read-only SQL."""


class SQLParseError(UnsafeQueryError):
    """Raised when text is not valid T-SQL."""


class MultipleStatementError(UnsafeQueryError):
    """Raised when more than one SQL statement is supplied."""


class UnsupportedStatementError(UnsafeQueryError):
    """Raised for non-query or otherwise unsupported statements."""


class UnauthorizedTableError(UnsafeQueryError):
    """Raised when a physical source is outside the active QuerySpace."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        table: str | None = None,
        column: str | None = None,
        operation: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code or AuthorizationErrorCode.TABLE_NOT_ALLOWED,
            report=report,
            table=table,
            column=column,
            operation=operation,
        )


class UnauthorizedColumnError(UnsafeQueryError):
    """Raised when a column is absent, denied, or policy-only."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        table: str | None = None,
        column: str | None = None,
        operation: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code or AuthorizationErrorCode.COLUMN_SELECT_NOT_ALLOWED,
            report=report,
            table=table,
            column=column,
            operation=operation,
        )


class ColumnOperationNotAllowedError(UnsafeQueryError):
    """Raised when a column is used for a denied SQL operation."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        table: str | None = None,
        column: str | None = None,
        operation: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code or AuthorizationErrorCode.COLUMN_SELECT_NOT_ALLOWED,
            report=report,
            table=table,
            column=column,
            operation=operation,
        )


class AmbiguousColumnError(UnsafeQueryError):
    """Raised when a column cannot be resolved to exactly one source."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        table: str | None = None,
        column: str | None = None,
        operation: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code or AuthorizationErrorCode.AMBIGUOUS_COLUMN,
            report=report,
            table=table,
            column=column,
            operation=operation,
        )


class UnauthorizedJoinError(UnsafeQueryError):
    """Raised when a join shape is disabled by execution policy."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        table: str | None = None,
        column: str | None = None,
        operation: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code or AuthorizationErrorCode.COLUMN_JOIN_NOT_ALLOWED,
            report=report,
            table=table,
            column=column,
            operation=operation,
        )


class RelationshipViolationError(UnauthorizedJoinError):
    """Raised when a join predicate does not match a strict relationship."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        table: str | None = None,
        column: str | None = None,
        operation: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code or AuthorizationErrorCode.RELATIONSHIP_NOT_ALLOWED,
            report=report,
            table=table,
            column=column,
            operation=operation,
        )


class SelectStarNotAllowedError(UnsafeQueryError, QueryShapeNotAllowedError):
    """Raised when projection wildcards are disabled or invalid."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        table: str | None = None,
        column: str | None = None,
        operation: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code or AuthorizationErrorCode.SELECT_STAR_NOT_ALLOWED,
            report=report,
            table=table,
            column=column,
            operation=operation,
        )


class ColumnOperation(str, Enum):
    """Security-relevant operation performed on a physical column."""

    SELECT = "SELECT"
    FILTER = "FILTER"
    SORT = "SORT"
    GROUP = "GROUP"
    AGGREGATE = "AGGREGATE"
    JOIN = "JOIN"


@dataclass(frozen=True)
class ParsedSQL:
    """One parsed, read-only T-SQL query."""

    original_sql: str
    expression: exp.Query


@dataclass(frozen=True)
class ColumnUsage:
    """Physical column and all operations observed across the query AST."""

    table: TableRef
    column: str
    operations: tuple[ColumnOperation, ...]


@dataclass(frozen=True)
class RelationshipUsage:
    """A strict relationship matched by an equality join."""

    relationship: RelationshipSpec


@dataclass(frozen=True)
class AuthorizationReport:
    """Immutable audit metadata from one authorization pass."""

    allowed: bool = True
    error_code: AuthorizationErrorCode | str | None = None
    tables_used: tuple[str, ...] = ()
    columns_used: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    access_profile: str | None = None
    injected_policies: tuple[str, ...] = ()
    applied_masks: tuple[str, ...] = ()
    hidden_columns: tuple[str, ...] = ()
    relationships_used: tuple[str, ...] = ()
    query_shape: Mapping[str, Any] = field(default_factory=dict)

    # Backward compatibility attributes
    referenced_tables: tuple[TableRef, ...] = ()
    referenced_columns: tuple[ColumnUsage, ...] = ()
    relationships: tuple[RelationshipUsage, ...] = ()
    projection: tuple[ProjectionColumn, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a clean, serializable dictionary representation of the report."""
        code_val = (
            self.error_code.value
            if isinstance(self.error_code, Enum)
            else self.error_code
        )
        return {
            "allowed": self.allowed,
            "error_code": code_val,
            "tables_used": list(self.tables_used),
            "columns_used": {k: list(v) for k, v in self.columns_used.items()},
            "access_profile": self.access_profile,
            "injected_policies": list(self.injected_policies),
            "applied_masks": list(self.applied_masks),
            "hidden_columns": list(self.hidden_columns),
            "relationships_used": list(self.relationships_used),
            "query_shape": dict(self.query_shape),
        }

    def model_dump(self) -> dict[str, Any]:
        """Alias for to_dict() for Pydantic / standard model compatibility."""
        return self.to_dict()

    def model_dump_json(self) -> str:
        """Return JSON string representation."""
        import json

        return json.dumps(self.to_dict(), indent=2)


@dataclass(frozen=True)
class _Binding:
    column: ResolvedColumn
    source_alias: str


_DANGEROUS_FUNCTIONS = {
    "OPENQUERY",
    "OPENROWSET",
    "OPENDATASOURCE",
    "XP_CMDSHELL",
    "OBJECT_ID",
    "DB_ID",
    "DB_NAME",
    "SUSER_SNAME",
    "SUSER_ID",
    "IS_SRVROLEMEMBER",
    "IS_MEMBER",
    "CURRENT_USER",
    "SYSTEM_USER",
    "SESSION_USER",
    "USER_NAME",
    "HOST_NAME",
}


class SQLParser:
    """Parse and validate one structurally read-only T-SQL query."""

    def parse(self, sql: str) -> ParsedSQL:
        if not isinstance(sql, str) or not sql.strip():
            raise SQLParseError("SQL query is empty.")
        try:
            statements = [item for item in parse(sql, read="tsql") if item is not None]
        except ParseError as error:
            raise SQLParseError("SQL query could not be parsed as T-SQL.") from error
        if len(statements) != 1:
            raise MultipleStatementError("Exactly one SQL statement is allowed.")
        statement = statements[0]
        if not isinstance(statement, exp.Query):
            raise UnsupportedStatementError(
                "Only read-only query statements are allowed."
            )
        if any(node.comments for node in statement.walk()):
            raise UnsupportedStatementError("SQL comments are not allowed.")
        if next(statement.find_all(exp.Into), None) is not None:
            raise UnsupportedStatementError("SELECT INTO is not allowed.")
        if any(
            isinstance(parameter.this, exp.Parameter)
            for parameter in statement.find_all(exp.Parameter)
        ):
            raise UnsupportedStatementError(
                "T-SQL system variables are not allowed in authorized SQL."
            )
        for table in statement.find_all(exp.Table):
            if not isinstance(table.this, exp.Identifier):
                raise UnsupportedStatementError(
                    "Table functions and external table sources are not allowed."
                )
        for function in statement.find_all(exp.Func):
            name = (
                function.name
                if isinstance(function, exp.Anonymous)
                else function.sql_name()
            ).upper()
            if name in _DANGEROUS_FUNCTIONS:
                raise UnsupportedStatementError(
                    f"Function {name!r} is not allowed in authorized SQL."
                )
        normalized = sql.strip()
        if normalized.endswith(";"):
            normalized = normalized[:-1].rstrip()
        return ParsedSQL(normalized, statement)


class SQLAuthorizer:
    """Authorize tables, columns, operations, wildcards, and joins from an AST."""

    def authorize(
        self,
        parsed: ParsedSQL,
        query_space: ResolvedQuerySpace | ProfiledQuerySpace,
        *,
        trusted_policy_columns: frozenset[tuple[tuple[str, str], str]] = frozenset(),
        trusted_derived_projection_star: bool = False,
    ) -> AuthorizationReport:
        if isinstance(query_space, ProfiledQuerySpace):
            profiled_space: ProfiledQuerySpace | None = query_space
            resolved_space: ResolvedQuerySpace = query_space.resolved_query_space
        elif isinstance(query_space, ResolvedQuerySpace):
            profiled_space = None
            resolved_space = query_space
        else:
            raise TypeError(
                "SQL authorization requires a ResolvedQuerySpace or ProfiledQuerySpace."
            )

        resolved_space.validate()
        try:
            scopes = list(traverse_scope(parsed.expression))
        except Exception as error:
            raise SQLParseError("SQL scopes could not be resolved safely.") from error

        self._check_query_shape(
            parsed.expression,
            scopes,
            resolved_space.execution_policy,
            trusted_derived_projection_star,
        )

        table_refs, logical_tables, source_maps = self._authorize_tables(
            parsed.expression, scopes, resolved_space, profiled_space
        )
        self._authorize_wildcards(
            parsed.expression,
            scopes,
            resolved_space,
            table_refs,
            source_maps,
            trusted_derived_projection_star,
        )
        outputs_by_scope: dict[int, dict[str, tuple[ResolvedColumn, ...]]] = {}
        usage: dict[
            tuple[tuple[str, str], str],
            tuple[ResolvedColumn, set[ColumnOperation]],
        ] = {}
        relationships: list[RelationshipUsage] = []
        for scope in scopes:
            outputs = self._build_output_lineage(
                scope, resolved_space, table_refs, source_maps, outputs_by_scope
            )
            outputs_by_scope[id(scope)] = outputs
            self._authorize_scope_columns(
                scope,
                resolved_space,
                table_refs,
                source_maps,
                outputs_by_scope,
                usage,
                trusted_policy_columns,
                profiled_space,
            )
            relationships.extend(
                self._authorize_scope_joins(
                    scope,
                    resolved_space,
                    table_refs,
                    source_maps,
                    outputs_by_scope,
                )
            )
            relationships.extend(
                self._authorize_scope_correlations(
                    scope,
                    resolved_space,
                    table_refs,
                    source_maps,
                    outputs_by_scope,
                )
            )
        visited = set(table_refs).union(logical_tables)
        for table in parsed.expression.find_all(exp.Table):
            if id(table) not in visited and not isinstance(table.parent, exp.Into):
                raise UnauthorizedTableError(
                    "A table source could not be resolved to a safe SQL scope."
                )
        referenced_tables = tuple(
            sorted(set(table_refs.values()), key=lambda item: item.identity_key)
        )
        referenced_columns = tuple(
            ColumnUsage(
                column.semantic.table,
                column.name,
                tuple(sorted(operations, key=lambda item: item.value)),
            )
            for _, (column, operations) in sorted(usage.items())
        )
        unique_relationships = {
            item.relationship.identity_key: item for item in relationships
        }
        projection = self._build_projection_metadata(
            parsed.expression,
            scopes,
            resolved_space,
            profiled_space,
            table_refs,
            source_maps,
        )
        tables_used = tuple(sorted({ref.full_name for ref in referenced_tables}))

        cols_by_op: dict[str, set[str]] = {}
        for _, (column, operations) in sorted(usage.items()):
            col_str = f"{column.semantic.table.full_name}.{column.name}"
            for op in operations:
                cols_by_op.setdefault(op.value, set()).add(col_str)
        columns_used = {
            op_key: tuple(sorted(cols)) for op_key, cols in sorted(cols_by_op.items())
        }

        profile_name = profiled_space.access_profile.name if profiled_space else None

        applied_masks: list[str] = []
        hidden_columns: list[str] = []
        if profiled_space:
            for ref in referenced_tables:
                resolved_table = resolved_space.get_table(ref)
                for col in resolved_table.columns:
                    eff = profiled_space.get_column_access(ref, col.name)
                    col_str = f"{ref.full_name}.{col.name}"
                    if eff is not None:
                        if eff.result_access == ResultAccess.MASKED:
                            applied_masks.append(col_str)
                        elif eff.result_access == ResultAccess.HIDDEN:
                            hidden_columns.append(col_str)

        rel_used_list = [
            f"{rel.relationship.source_table.full_name}.{rel.relationship.source_column} -> "
            f"{rel.relationship.target_table.full_name}.{rel.relationship.target_column}"
            for rel in unique_relationships.values()
        ]

        query_shape = {
            "joins_count": len(list(parsed.expression.find_all(exp.Join))),
            "has_subqueries": any(
                s.is_subquery or s.is_derived_table or s.is_correlated_subquery
                for s in scopes
            ),
            "has_ctes": any(s.is_cte for s in scopes),
            "has_unions": any(s.is_union for s in scopes),
        }

        return AuthorizationReport(
            allowed=True,
            error_code=None,
            tables_used=tables_used,
            columns_used=columns_used,
            access_profile=profile_name,
            injected_policies=(),
            applied_masks=tuple(sorted(set(applied_masks))),
            hidden_columns=tuple(sorted(set(hidden_columns))),
            relationships_used=tuple(sorted(set(rel_used_list))),
            query_shape=query_shape,
            referenced_tables=referenced_tables,
            referenced_columns=referenced_columns,
            relationships=tuple(
                unique_relationships[key] for key in sorted(unique_relationships)
            ),
            projection=projection,
        )

    def _check_query_shape(
        self,
        expression: exp.Query,
        scopes: list[Scope],
        exec_policy: ExecutionPolicy,
        trusted_derived_projection_star: bool,
    ) -> None:
        joins = list(expression.find_all(exp.Join))
        if len(joins) > exec_policy.max_joins:
            raise TooManyJoinsError(
                f"Query contains {len(joins)} joins, exceeding the allowed limit of {exec_policy.max_joins}."
            )

        if not exec_policy.allow_subqueries:
            subqueries = [
                s
                for s in scopes
                if s.is_subquery or s.is_derived_table or s.is_correlated_subquery
            ]
            if subqueries:
                raise SubqueryNotAllowedError(
                    "Subqueries are disabled by the active execution policy."
                )

        if not exec_policy.allow_ctes and expression.find(exp.With) is not None:
            raise CTENotAllowedError(
                "CTEs are disabled by the active execution policy."
            )

        if (
            not exec_policy.allow_cross_join
            and JoinType.CROSS not in exec_policy.allowed_join_types
        ):
            for join in joins:
                if join.kind and join.kind.upper() == "CROSS":
                    raise UnauthorizedJoinError(
                        "CROSS JOIN is disabled by the active execution policy."
                    )
            for scope in scopes:
                scope_joins = list(scope.expression.find_all(exp.Join))
                if len(scope.selected_sources) > 1 and not scope_joins:
                    raise UnauthorizedJoinError(
                        "Comma cross joins are disabled by the active execution policy."
                    )

        if not exec_policy.allow_select_star and not trusted_derived_projection_star:
            for star in expression.find_all(exp.Star):
                if star.find_ancestor(exp.Count, exp.AggFunc) is None:
                    raise SelectStarNotAllowedError(
                        "Only COUNT(*) is allowed as a wildcard; SELECT * and column.* are forbidden."
                    )

    def _build_projection_metadata(
        self,
        expression: exp.Query,
        scopes: list[Scope],
        query_space: ResolvedQuerySpace,
        profiled_space: ProfiledQuerySpace | None,
        table_refs: dict[int, TableRef],
        source_maps: dict[int, dict[str, exp.Table | Scope]],
    ) -> tuple[ProjectionColumn, ...]:
        root_scope = scopes[0] if scopes else None
        if not root_scope or not isinstance(root_scope.expression, exp.Select):
            return ()

        proj_cols: list[ProjectionColumn] = []
        select_expr = root_scope.expression
        for item in select_expr.expressions:
            output_name = item.alias_or_name
            columns_in_item = list(item.find_all(exp.Column))

            is_simple = isinstance(item, exp.Column) or (
                isinstance(item, exp.Alias) and isinstance(item.this, exp.Column)
            )

            leaf_cols: list[tuple[TableRef, str]] = []
            for col_node in columns_in_item:
                col_name = col_node.name
                table_node = col_node.find(exp.Table)
                t_ref: TableRef | None = None
                if id(col_node) in table_refs:
                    t_ref = table_refs[id(col_node)]
                elif table_node and id(table_node) in table_refs:
                    t_ref = table_refs[id(table_node)]
                elif col_node.table:
                    src_map = source_maps.get(id(root_scope), {})
                    raw_src = src_map.get(col_node.table.casefold())
                    if isinstance(raw_src, exp.Table) and id(raw_src) in table_refs:
                        t_ref = table_refs[id(raw_src)]
                else:
                    src_map = source_maps.get(id(root_scope), {})
                    if len(src_map) == 1:
                        single_src = next(iter(src_map.values()))
                        if (
                            isinstance(single_src, exp.Table)
                            and id(single_src) in table_refs
                        ):
                            t_ref = table_refs[id(single_src)]

                if t_ref is not None:
                    leaf_cols.append((t_ref, col_name))

            if is_simple and leaf_cols:
                src_ref, src_col = leaf_cols[0]
                res_access = (
                    profiled_space.get_result_access(src_ref, src_col)
                    if profiled_space
                    else ResultAccess.VISIBLE
                )
                masking = (
                    profiled_space.get_masking_policy(src_ref, src_col)
                    if profiled_space
                    else None
                )
                proj_cols.append(
                    ProjectionColumn(
                        output_name=output_name,
                        source_table=src_ref,
                        source_column=src_col,
                        result_access=res_access,
                        masking_policy=masking,
                        is_expression=False,
                        leaf_columns=tuple(leaf_cols),
                    )
                )
            else:
                expr_res_access = ResultAccess.VISIBLE
                expr_masking = None

                for leaf_ref, leaf_col in leaf_cols:
                    l_res = (
                        profiled_space.get_result_access(leaf_ref, leaf_col)
                        if profiled_space
                        else ResultAccess.VISIBLE
                    )
                    if l_res == ResultAccess.HIDDEN:
                        raise HiddenColumnExposureError(
                            f"Expression {item.sql()!r} references hidden column {leaf_ref.full_name}.{leaf_col}."
                        )
                    if l_res == ResultAccess.MASKED:
                        raise UnsupportedMaskedExpressionError(
                            f"Expression {item.sql()!r} transforms masked column {leaf_ref.full_name}.{leaf_col}."
                        )

                proj_cols.append(
                    ProjectionColumn(
                        output_name=output_name,
                        source_table=None,
                        source_column=None,
                        result_access=expr_res_access,
                        masking_policy=expr_masking,
                        is_expression=True,
                        leaf_columns=tuple(leaf_cols),
                    )
                )

        return tuple(proj_cols)

    def _authorize_tables(
        self,
        expression: exp.Query,
        scopes: list[Scope],
        query_space: ResolvedQuerySpace,
        profiled_space: ProfiledQuerySpace | None = None,
    ) -> tuple[dict[int, TableRef], set[int], dict[int, dict[str, exp.Table | Scope]]]:
        table_refs: dict[int, TableRef] = {}
        logical_tables: set[int] = set()
        source_maps: dict[int, dict[str, exp.Table | Scope]] = {}
        for scope in scopes:
            sources: dict[str, exp.Table | Scope] = {}
            for alias, (node, source) in scope.selected_sources.items():
                key = alias.casefold()
                if key in sources:
                    raise UnauthorizedTableError(
                        f"Duplicate source alias {alias!r} is not allowed."
                    )
                sources[key] = source
                if isinstance(source, Scope):
                    if isinstance(node, exp.Table):
                        logical_tables.add(id(node))
                    continue
                if not isinstance(source, exp.Table) or not isinstance(
                    source.this, exp.Identifier
                ):
                    raise UnauthorizedTableError(
                        "Only physical tables, CTEs, and derived queries are allowed."
                    )
                if source.catalog:
                    raise UnauthorizedTableError(
                        "Database- or server-qualified table names are not allowed."
                    )
                ref = self._resolve_table_ref(source, query_space)
                if profiled_space is not None and not profiled_space.is_table_available(
                    ref
                ):
                    raise UnauthorizedTableError(
                        f"Table {ref.full_name!r} is disabled under profile {profiled_space.access_profile.name!r}."
                    )
                table_refs[id(source)] = ref
            source_maps[id(scope)] = sources
        return table_refs, logical_tables, source_maps

    def _resolve_table_ref(
        self, table: exp.Table, query_space: ResolvedQuerySpace
    ) -> TableRef:
        if table.db:
            ref = TableRef(table.db, table.name)
            if ref not in query_space.table_refs:
                raise UnauthorizedTableError(
                    f"Table {ref.full_name!r} is outside the active QuerySpace."
                )
            return ref
        if not query_space.execution_policy.allow_unqualified_tables:
            raise UnauthorizedTableError(
                f"Table {table.name!r} must be referenced as schema.table."
            )
        matches = [
            ref
            for ref in query_space.table_refs
            if ref.table.casefold() == table.name.casefold()
        ]
        if len(matches) != 1:
            raise UnauthorizedTableError(
                f"Unqualified table {table.name!r} is ambiguous or unavailable."
            )
        return matches[0]

    def _authorize_scope_columns(
        self,
        scope: Scope,
        query_space: ResolvedQuerySpace,
        table_refs: dict[int, TableRef],
        source_maps: dict[int, dict[str, exp.Table | Scope]],
        outputs_by_scope: dict[int, dict[str, tuple[ResolvedColumn, ...]]],
        usage: dict[
            tuple[tuple[str, str], str],
            tuple[ResolvedColumn, set[ColumnOperation]],
        ],
        trusted_policy_columns: frozenset[tuple[tuple[str, str], str]],
        profiled_space: ProfiledQuerySpace | None = None,
    ) -> None:
        columns = list(scope.columns)
        if isinstance(scope.expression, exp.Select):
            order = scope.expression.args.get("order")
            if isinstance(order, exp.Order):
                seen = {id(column) for column in columns}
                columns.extend(
                    column
                    for column in order.find_all(exp.Column)
                    if id(column) not in seen
                )
        for column in columns:
            if not column.name or column.name == "*":
                continue
            bindings = self._resolve_column(
                column,
                scope,
                query_space,
                table_refs,
                source_maps,
                outputs_by_scope,
            )
            operations = self._column_operations(column)
            if not bindings:
                op_code = (
                    AuthorizationErrorCode.COLUMN_FILTER_NOT_ALLOWED
                    if ColumnOperation.FILTER in operations
                    else AuthorizationErrorCode.COLUMN_SELECT_NOT_ALLOWED
                )
                raise UnauthorizedColumnError(
                    f"Column {column.name!r} is outside the active QuerySpace.",
                    code=op_code,
                    column=column.name,
                )
            for binding in bindings:
                resolved = binding.column
                identity = resolved.semantic.identity_key
                trusted = identity in trusted_policy_columns
                eff_access = (
                    profiled_space.get_column_access(
                        resolved.semantic.table, resolved.name
                    )
                    if profiled_space
                    else None
                )
                if resolved.access is ColumnAccessLevel.DENIED or (
                    eff_access
                    and eff_access.capabilities is not None
                    and not eff_access.capabilities.any_enabled
                    and eff_access.result_access == ResultAccess.HIDDEN
                ):
                    op_code = (
                        AuthorizationErrorCode.COLUMN_FILTER_NOT_ALLOWED
                        if ColumnOperation.FILTER in operations
                        else AuthorizationErrorCode.COLUMN_SELECT_NOT_ALLOWED
                    )
                    raise UnauthorizedColumnError(
                        f"Column {resolved.semantic.table.full_name}."
                        f"{resolved.name!s} is denied.",
                        code=op_code,
                        table=resolved.semantic.table.full_name,
                        column=resolved.name,
                    )
                if resolved.access is ColumnAccessLevel.POLICY_ONLY and not trusted:
                    raise UnauthorizedColumnError(
                        f"Column {resolved.semantic.table.full_name}."
                        f"{resolved.name!s} is reserved for mandatory policy enforcement.",
                        code=AuthorizationErrorCode.COLUMN_SELECT_NOT_ALLOWED,
                        table=resolved.semantic.table.full_name,
                        column=resolved.name,
                    )
                if trusted and not set(operations).issubset(
                    {ColumnOperation.FILTER, ColumnOperation.JOIN}
                ):
                    raise UnauthorizedColumnError(
                        f"Policy column {resolved.semantic.table.full_name}."
                        f"{resolved.name!s} appears outside an injected predicate.",
                        code=AuthorizationErrorCode.COLUMN_SELECT_NOT_ALLOWED,
                        table=resolved.semantic.table.full_name,
                        column=resolved.name,
                    )
                if not trusted:
                    caps = (
                        profiled_space.get_effective_capabilities(
                            resolved.semantic.table, resolved.name
                        )
                        if profiled_space
                        else resolved.capabilities
                    )
                    op_code_map = {
                        ColumnOperation.SELECT: AuthorizationErrorCode.COLUMN_SELECT_NOT_ALLOWED,
                        ColumnOperation.FILTER: AuthorizationErrorCode.COLUMN_FILTER_NOT_ALLOWED,
                        ColumnOperation.GROUP: AuthorizationErrorCode.COLUMN_GROUP_NOT_ALLOWED,
                        ColumnOperation.SORT: AuthorizationErrorCode.COLUMN_SORT_NOT_ALLOWED,
                        ColumnOperation.AGGREGATE: AuthorizationErrorCode.COLUMN_AGGREGATE_NOT_ALLOWED,
                        ColumnOperation.JOIN: AuthorizationErrorCode.COLUMN_JOIN_NOT_ALLOWED,
                    }
                    for operation in operations:
                        if not caps.allows(operation.value):
                            raise ColumnOperationNotAllowedError(
                                f"Column {resolved.semantic.table.full_name}."
                                f"{resolved.name!s} is not allowed in "
                                f"{operation.value} operations.",
                                code=op_code_map.get(
                                    operation,
                                    AuthorizationErrorCode.COLUMN_SELECT_NOT_ALLOWED,
                                ),
                                table=resolved.semantic.table.full_name,
                                column=resolved.name,
                                operation=operation.value,
                            )
                record = usage.setdefault(identity, (resolved, set()))
                record[1].update(operations)

    def _resolve_column(
        self,
        column: exp.Column,
        scope: Scope,
        query_space: ResolvedQuerySpace,
        table_refs: dict[int, TableRef],
        source_maps: dict[int, dict[str, exp.Table | Scope]],
        outputs_by_scope: dict[int, dict[str, tuple[ResolvedColumn, ...]]],
    ) -> tuple[_Binding, ...]:
        if column.table:
            found = self._find_source(scope, column.table, source_maps)
            if found is None:
                raise UnauthorizedColumnError(
                    f"Column qualifier {column.table!r} is not available in this scope."
                )
            source_alias, source = found
            bindings = self._source_column_bindings(
                column.name,
                source_alias,
                source,
                query_space,
                table_refs,
                outputs_by_scope,
            )
            if bindings is None:
                raise UnauthorizedColumnError(
                    f"Column {column.name!r} is not exposed by its SQL source."
                )
            return bindings
        if self._is_order_alias(column, scope, outputs_by_scope):
            columns = outputs_by_scope[id(scope)][column.name.casefold()]
            return tuple(_Binding(item, column.name.casefold()) for item in columns)
        current: Scope | None = scope
        while current is not None:
            matches: list[tuple[_Binding, ...]] = []
            for alias, source in source_maps.get(id(current), {}).items():
                exposed = self._source_column_bindings(
                    column.name,
                    alias,
                    source,
                    query_space,
                    table_refs,
                    outputs_by_scope,
                )
                if exposed is not None:
                    matches.append(exposed)
            if len(matches) > 1:
                raise AmbiguousColumnError(
                    f"Unqualified column {column.name!r} is ambiguous in this scope."
                )
            if len(matches) == 1:
                return matches[0]
            current = current.parent
        return ()

    def _find_source(
        self,
        scope: Scope,
        qualifier: str,
        source_maps: dict[int, dict[str, exp.Table | Scope]],
    ) -> tuple[str, exp.Table | Scope] | None:
        key = qualifier.casefold()
        current: Scope | None = scope
        while current is not None:
            source = source_maps.get(id(current), {}).get(key)
            if source is not None:
                return key, source
            current = current.parent
        return None

    def _source_column_bindings(
        self,
        name: str,
        alias: str,
        source: exp.Table | Scope,
        query_space: ResolvedQuerySpace,
        table_refs: dict[int, TableRef],
        outputs_by_scope: dict[int, dict[str, tuple[ResolvedColumn, ...]]],
    ) -> tuple[_Binding, ...] | None:
        if isinstance(source, Scope):
            columns = outputs_by_scope.get(id(source), {}).get(name.casefold())
            if columns is None:
                return None
            return tuple(_Binding(column, alias) for column in columns)
        ref = table_refs.get(id(source))
        if ref is None:
            return None
        try:
            column = query_space.get_table(ref).get_column(name)
        except KeyError:
            return None
        return (_Binding(column, alias),)

    def _build_output_lineage(
        self,
        scope: Scope,
        query_space: ResolvedQuerySpace,
        table_refs: dict[int, TableRef],
        source_maps: dict[int, dict[str, exp.Table | Scope]],
        outputs_by_scope: dict[int, dict[str, tuple[ResolvedColumn, ...]]],
    ) -> dict[str, tuple[ResolvedColumn, ...]]:
        if scope.is_union:
            union_outputs: dict[str, tuple[ResolvedColumn, ...]] = {}
            child_outputs = [
                outputs_by_scope.get(id(item), {}) for item in scope.union_scopes
            ]
            union_expression = cast(exp.Query, scope.expression)
            for index, name in enumerate(union_expression.named_selects):
                union_columns: list[ResolvedColumn] = []
                for child in child_outputs:
                    values = list(child.values())
                    if index < len(values):
                        union_columns.extend(values[index])
                union_outputs[name.casefold()] = self._deduplicate_columns(
                    union_columns
                )
            return union_outputs
        if not isinstance(scope.expression, exp.Select):
            return {}
        outputs: dict[str, tuple[ResolvedColumn, ...]] = {}
        for expression in scope.expression.expressions:
            output_name = expression.alias_or_name
            if not output_name:
                continue
            columns: list[ResolvedColumn] = []
            for column in expression.find_all(exp.Column):
                if (
                    column.name == "*"
                    or column.find_ancestor(exp.Select) is not scope.expression
                ):
                    continue
                try:
                    bindings = self._resolve_column(
                        column,
                        scope,
                        query_space,
                        table_refs,
                        source_maps,
                        outputs_by_scope,
                    )
                except SQLAuthorizationError:
                    continue
                columns.extend(binding.column for binding in bindings)
            outputs[output_name.casefold()] = self._deduplicate_columns(columns)
        return outputs

    def _authorize_wildcards(
        self,
        expression: exp.Query,
        scopes: list[Scope],
        query_space: ResolvedQuerySpace,
        table_refs: dict[int, TableRef],
        source_maps: dict[int, dict[str, exp.Table | Scope]],
        trusted_derived_projection_star: bool,
    ) -> None:
        for star in expression.find_all(exp.Star):
            if isinstance(star.parent, exp.Count):
                continue
            scope = self._scope_for_node(star, scopes)
            if scope is None:
                raise SelectStarNotAllowedError("Wildcard scope could not be resolved.")
            sources = source_maps.get(id(scope), {})
            if (
                trusted_derived_projection_star
                and not isinstance(star.parent, exp.Column)
                and len(sources) == 1
                and all(isinstance(source, Scope) for source in sources.values())
            ):
                # SQLGlot renders TOP over a T-SQL set operation as a synthetic
                # SELECT * over the already-authorized projected set. This star
                # was not present in user SQL and cannot expose extra base columns.
                continue
            if not query_space.execution_policy.allow_select_star:
                raise SelectStarNotAllowedError(
                    "Projection wildcards are disabled; only COUNT(*) is allowed."
                )
            if isinstance(star.parent, exp.Column):
                qualifier = star.parent.table
                found = self._find_source(scope, qualifier, source_maps)
                if found is None:
                    raise SelectStarNotAllowedError(
                        "Qualified wildcard source could not be resolved."
                    )
                sources = {found[0]: found[1]}
            if not sources or any(
                not self._source_allows_star(source, query_space, table_refs)
                for source in sources.values()
            ):
                raise SelectStarNotAllowedError(
                    "Wildcard requires every physical source column to be user-selectable "
                    "with no denied columns."
                )

    def _source_allows_star(
        self,
        source: exp.Table | Scope,
        query_space: ResolvedQuerySpace,
        table_refs: dict[int, TableRef],
    ) -> bool:
        if isinstance(source, Scope):
            return False
        ref = table_refs.get(id(source))
        if ref is None:
            return False
        table = query_space.get_table(ref)
        return (
            not table.denied_columns
            and bool(table.columns)
            and all(
                column.access is ColumnAccess.USER_ALLOWED
                and column.capabilities.selectable
                for column in table.columns
            )
        )

    def _authorize_scope_joins(
        self,
        scope: Scope,
        query_space: ResolvedQuerySpace,
        table_refs: dict[int, TableRef],
        source_maps: dict[int, dict[str, exp.Table | Scope]],
        outputs_by_scope: dict[int, dict[str, tuple[ResolvedColumn, ...]]],
    ) -> list[RelationshipUsage]:
        if not isinstance(scope.expression, exp.Select):
            return []
        used: list[RelationshipUsage] = []
        prior_aliases: set[str] = set()
        from_clause = scope.expression.args.get("from_")
        if isinstance(from_clause, exp.From) and from_clause.this is not None:
            prior_aliases.add(from_clause.this.alias_or_name.casefold())
        for join in scope.expression.args.get("joins") or ():
            join_type = self._join_type(join)
            if join_type not in query_space.execution_policy.allowed_join_types:
                raise UnauthorizedJoinError(
                    f"Join type {join_type.value!r} is disabled by execution policy."
                )
            joined_alias = join.this.alias_or_name.casefold()
            if join_type in {JoinType.CROSS, JoinType.APPLY}:
                prior_aliases.add(joined_alias)
                continue
            on = join.args.get("on")
            if on is None:
                raise UnauthorizedJoinError(
                    "Implicit and predicate-free joins are not allowed."
                )
            if next(on.find_all(exp.Or), None) is not None or isinstance(on, exp.Or):
                raise UnauthorizedJoinError("OR join predicates are not authorized.")
            matched_target = False
            for predicate in self._and_terms(on):
                columns = list(predicate.find_all(exp.Column))
                aliases = {
                    column.table.casefold() for column in columns if column.table
                }
                if len(aliases) <= 1:
                    continue
                if (
                    not isinstance(predicate, exp.EQ)
                    or not isinstance(predicate.left, exp.Column)
                    or not isinstance(predicate.right, exp.Column)
                ):
                    raise RelationshipViolationError(
                        "Cross-source join predicates must be direct column equality."
                    )
                left = self._resolve_column(
                    predicate.left,
                    scope,
                    query_space,
                    table_refs,
                    source_maps,
                    outputs_by_scope,
                )
                right = self._resolve_column(
                    predicate.right,
                    scope,
                    query_space,
                    table_refs,
                    source_maps,
                    outputs_by_scope,
                )
                if len(left) != 1 or len(right) != 1:
                    raise RelationshipViolationError(
                        "Join endpoints must resolve to one physical column each."
                    )
                if joined_alias not in {left[0].source_alias, right[0].source_alias}:
                    continue
                if not ({left[0].source_alias, right[0].source_alias} & prior_aliases):
                    continue
                relationship = self._matching_strict_relationship(
                    left[0].column, right[0].column, query_space.relationships
                )
                strict_for_pair = self._strict_relationship_exists(
                    left[0].column,
                    right[0].column,
                    query_space.relationships,
                )
                if relationship is not None:
                    used.append(RelationshipUsage(relationship))
                    matched_target = True
                elif (
                    strict_for_pair
                    or not query_space.execution_policy.allow_unlisted_joins
                ):
                    raise RelationshipViolationError(
                        "Join endpoints do not match an authorized strict relationship."
                    )
                else:
                    matched_target = True
            if (
                not matched_target
                and not query_space.execution_policy.allow_unlisted_joins
            ):
                raise UnauthorizedJoinError(
                    "Join does not contain an authorized relationship for its target source."
                )
            prior_aliases.add(joined_alias)
        return used

    def _authorize_scope_correlations(
        self,
        scope: Scope,
        query_space: ResolvedQuerySpace,
        table_refs: dict[int, TableRef],
        source_maps: dict[int, dict[str, exp.Table | Scope]],
        outputs_by_scope: dict[int, dict[str, tuple[ResolvedColumn, ...]]],
    ) -> list[RelationshipUsage]:
        used: list[RelationshipUsage] = []
        for external in scope.external_columns:
            if not external.table:
                continue
            qualifier = external.table.casefold()
            if qualifier in source_maps.get(id(scope), {}):
                continue
            parent = scope.parent
            if (
                parent is None
                or self._find_source(parent, external.table, source_maps) is None
            ):
                continue
            comparison = external.find_ancestor(
                exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE
            )
            if comparison is None:
                raise RelationshipViolationError(
                    "Correlated columns require a direct comparison predicate."
                )
            if not isinstance(comparison, exp.EQ):
                raise RelationshipViolationError(
                    "Correlated table relationships require column equality."
                )
            left_expression = comparison.left
            right_expression = comparison.right
            if not isinstance(left_expression, exp.Column) or not isinstance(
                right_expression, exp.Column
            ):
                raise RelationshipViolationError(
                    "Correlated relationship endpoints must be direct columns."
                )
            left = self._resolve_column(
                left_expression,
                scope,
                query_space,
                table_refs,
                source_maps,
                outputs_by_scope,
            )
            right = self._resolve_column(
                right_expression,
                scope,
                query_space,
                table_refs,
                source_maps,
                outputs_by_scope,
            )
            if len(left) != 1 or len(right) != 1:
                raise RelationshipViolationError(
                    "Correlated endpoints must resolve to one physical column each."
                )
            relationship = self._matching_strict_relationship(
                left[0].column, right[0].column, query_space.relationships
            )
            strict_for_pair = self._strict_relationship_exists(
                left[0].column, right[0].column, query_space.relationships
            )
            if relationship is not None:
                used.append(RelationshipUsage(relationship))
            elif (
                strict_for_pair or not query_space.execution_policy.allow_unlisted_joins
            ):
                raise RelationshipViolationError(
                    "Correlated predicate does not match an authorized strict relationship."
                )
        return used

    @staticmethod
    def _matching_strict_relationship(
        left: ResolvedColumn,
        right: ResolvedColumn,
        relationships: Collection[RelationshipSpec],
    ) -> RelationshipSpec | None:
        left_endpoint = (left.semantic.table, left.name.casefold())
        right_endpoint = (right.semantic.table, right.name.casefold())
        for relationship in relationships:
            if not relationship.strict:
                continue
            source = (relationship.source_table, relationship.source_column.casefold())
            target = (relationship.target_table, relationship.target_column.casefold())
            if {left_endpoint, right_endpoint} == {source, target}:
                return relationship
        return None

    @staticmethod
    def _strict_relationship_exists(
        left: ResolvedColumn,
        right: ResolvedColumn,
        relationships: Collection[RelationshipSpec],
    ) -> bool:
        pair = {left.semantic.table, right.semantic.table}
        return any(
            relationship.strict
            and {relationship.source_table, relationship.target_table} == pair
            for relationship in relationships
        )

    @staticmethod
    def _join_type(join: exp.Join) -> JoinType:
        if isinstance(join.this, exp.Lateral):
            return JoinType.APPLY
        side = (join.side or "").upper()
        kind = (join.kind or "").upper()
        if kind == "CROSS":
            return JoinType.CROSS
        if not side and not kind and join.args.get("on") is None:
            raise UnauthorizedJoinError("Implicit comma joins are not allowed.")
        return {
            "LEFT": JoinType.LEFT,
            "RIGHT": JoinType.RIGHT,
            "FULL": JoinType.FULL,
        }.get(side, JoinType.INNER)

    @staticmethod
    def _column_operations(column: exp.Column) -> tuple[ColumnOperation, ...]:
        operations: list[ColumnOperation] = []
        if column.find_ancestor(exp.Join) is not None:
            operations.append(ColumnOperation.JOIN)
        if column.find_ancestor(exp.Where, exp.Having) is not None:
            operations.append(ColumnOperation.FILTER)
        if column.find_ancestor(exp.Order) is not None:
            operations.append(ColumnOperation.SORT)
        if column.find_ancestor(exp.Group) is not None:
            operations.append(ColumnOperation.GROUP)
        window = column.find_ancestor(exp.Window)
        if (
            window is not None
            and column.find_ancestor(exp.Order) is None
            and any(
                column is item or column in set(item.walk())
                for item in window.args.get("partition_by") or ()
            )
        ):
            operations.append(ColumnOperation.GROUP)

        if column.find_ancestor(exp.AggFunc) is not None:
            operations.append(ColumnOperation.AGGREGATE)
        return tuple(dict.fromkeys(operations)) or (ColumnOperation.SELECT,)

    @staticmethod
    def _is_order_alias(
        column: exp.Column,
        scope: Scope,
        outputs_by_scope: dict[int, dict[str, tuple[ResolvedColumn, ...]]],
    ) -> bool:
        return column.find_ancestor(
            exp.Order
        ) is not None and column.name.casefold() in outputs_by_scope.get(id(scope), {})

    @staticmethod
    def _scope_for_node(node: exp.Expression, scopes: list[Scope]) -> Scope | None:
        select = node.find_ancestor(exp.Select)
        return next((scope for scope in scopes if scope.expression is select), None)

    @staticmethod
    def _and_terms(expression: exp.Expression) -> tuple[exp.Expression, ...]:
        if isinstance(expression, exp.Paren):
            return SQLAuthorizer._and_terms(cast(exp.Expression, expression.this))
        if isinstance(expression, exp.And):
            return SQLAuthorizer._and_terms(
                cast(exp.Expression, expression.left)
            ) + SQLAuthorizer._and_terms(cast(exp.Expression, expression.right))
        return (expression,)

    @staticmethod
    def _deduplicate_columns(
        columns: list[ResolvedColumn],
    ) -> tuple[ResolvedColumn, ...]:
        unique: dict[tuple[tuple[str, str], str], ResolvedColumn] = {}
        for column in columns:
            unique[column.semantic.identity_key] = column
        return tuple(unique.values())
