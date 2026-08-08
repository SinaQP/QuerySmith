"""Deterministic, capability-rich LLM context construction."""

from __future__ import annotations

from dataclasses import dataclass

from querysmith.catalog import format_type
from querysmith.models import (
    ColumnAccessLevel,
    ProfiledQuerySpace,
    ResolvedColumn,
    ResolvedQuerySpace,
    ResolvedTable,
    ResultAccess,
)
from querysmith.semantic import ContextBuildError, DataSensitivity


@dataclass(frozen=True)
class ContextBuilderOptions:
    include_examples: bool = True
    include_denied_columns: bool = False
    max_examples_per_column: int = 3
    max_description_length: int = 500

    def __post_init__(self) -> None:
        if not 0 <= self.max_examples_per_column <= 10:
            raise ContextBuildError("max_examples_per_column must be between 0 and 10.")
        if not 50 <= self.max_description_length <= 2000:
            raise ContextBuildError(
                "max_description_length must be between 50 and 2000."
            )


class ContextBuilder:
    """Build compact semantic context from a ResolvedQuerySpace or ProfiledQuerySpace."""

    def __init__(self, options: ContextBuilderOptions | None = None) -> None:
        self.options = options or ContextBuilderOptions()

    def build(self, query_space: ResolvedQuerySpace | ProfiledQuerySpace) -> str:
        if isinstance(query_space, ProfiledQuerySpace):
            profiled_space: ProfiledQuerySpace | None = query_space
            res_space: ResolvedQuerySpace = query_space.resolved_query_space
        elif isinstance(query_space, ResolvedQuerySpace):
            profiled_space = None
            res_space = query_space
        else:
            raise ContextBuildError(
                "ContextBuilder requires a ResolvedQuerySpace or ProfiledQuerySpace."
            )

        res_space.validate()
        lines = [
            "QUERY SPACE",
            "",
            "General rules:",
            "- Use only the physical tables and columns listed below.",
            "- Semantic names and synonyms are explanatory only.",
            "- SQL must use physical schema-qualified table names and physical column names.",
            "- Respect every allowed-operation capability.",
            "- Business rules are advisory unless explicitly marked enforceable.",
            "- Never invent relationships or use denied objects.",
        ]
        for table in sorted(res_space.tables, key=lambda item: item.ref.identity_key):
            if not isinstance(table, ResolvedTable):
                raise ContextBuildError("QuerySpace contains an unresolved table.")
            if profiled_space is not None and not profiled_space.is_table_available(
                table.ref
            ):
                continue
            lines.extend(self._table_lines(table, profiled_space))
        lines.extend(self._relationship_lines(res_space, profiled_space))
        return "\n".join(lines).rstrip()

    def _table_lines(
        self, table: ResolvedTable, profiled_space: ProfiledQuerySpace | None = None
    ) -> list[str]:
        entity = table.semantic.entity_name or table.ref.table
        lines = [
            "",
            f"ENTITY: {entity}",
            f"Physical table: {table.ref.full_name} (SQL: {_quoted_table(table)})",
        ]
        if table.semantic.entity_name:
            lines.append(f"semantic alias: {table.semantic.entity_name}")
        if table.semantic.synonyms:
            lines.append("Synonyms: " + ", ".join(table.semantic.synonyms))
        if table.semantic.description:
            lines.extend(
                [
                    "Purpose:",
                    _truncate(
                        table.semantic.description, self.options.max_description_length
                    ),
                ]
            )
        lines.append("Allowed columns:")
        user_columns = []
        for column in table.columns:
            if profiled_space is not None:
                c_acc = profiled_space.get_column_access(table.ref, column.name)
                eff_caps = profiled_space.get_effective_capabilities(
                    table.ref, column.name
                )
                if (
                    c_acc is not None
                    and c_acc.result_access == ResultAccess.HIDDEN
                    and not eff_caps.any_enabled
                ):
                    continue
                if (
                    column.access is ColumnAccessLevel.POLICY_ONLY
                    or column.access is ColumnAccessLevel.DENIED
                ):
                    continue
                user_columns.append(column)
            else:
                if column.access is ColumnAccessLevel.USER_ALLOWED:
                    user_columns.append(column)

        for column in sorted(user_columns, key=lambda item: item.identity_key):
            lines.extend(self._column_lines(column, profiled_space, table))
        if (
            self.options.include_denied_columns
            and table.denied_columns
            and profiled_space is None
        ):
            lines.append("Denied columns:")
            lines.extend(
                f"- {name}: DENIED for SELECT, FILTER, SORT, GROUP, AGGREGATE, and JOIN."
                for name in sorted(table.denied_columns, key=str.casefold)
            )
        if table.semantic.business_rules:
            lines.append("Business rules (advisory):")
            lines.extend(
                f"- {rule.description}" for rule in table.semantic.business_rules
            )
        if table.semantic.interpretation_warnings:
            lines.append("Interpretation warnings:")
            lines.extend(
                f"- {warning}" for warning in table.semantic.interpretation_warnings
            )
        return lines

    def _column_lines(
        self,
        column: ResolvedColumn,
        profiled_space: ProfiledQuerySpace | None = None,
        table: ResolvedTable | None = None,
    ) -> list[str]:
        physical_type = format_type(
            column.data_type,
            length=column.length,
            precision=column.precision,
            scale=column.scale,
        )
        markers = [physical_type, "NULL" if column.nullable else "NOT NULL"]
        if column.primary_key:
            markers.append("PK")
        legacy_markers = []
        if column.primary_key:
            legacy_markers.append("PK")
        if column.nullable:
            legacy_markers.append("nullable")
        legacy_suffix = f" [{' '.join(legacy_markers)}]" if legacy_markers else ""
        lines = [
            f"- {column.name} {physical_type}{legacy_suffix}",
            f"  Physical column: {_quote(column.name)} ({', '.join(markers)})",
        ]
        semantic = column.semantic
        if semantic.alias:
            lines.append(f"  Semantic name: {semantic.alias}")
            lines.append(f"  semantic alias: {semantic.alias}")
        if semantic.description:
            lines.append(
                "  Meaning: "
                + _truncate(semantic.description, self.options.max_description_length)
            )
        if semantic.synonyms:
            lines.append("  Synonyms: " + ", ".join(semantic.synonyms))
        if semantic.semantic_type is not None:
            value = getattr(semantic.semantic_type, "value", semantic.semantic_type)
            lines.append(f"  Semantic type: {value}")
        if semantic.unit:
            lines.append(f"  Unit: {semantic.unit}")
        caps = (
            profiled_space.get_effective_capabilities(table.ref, column.name)
            if profiled_space and table
            else column.capabilities
        )
        operations = caps.allowed_operations
        lines.append(
            "  Allowed operations: " + (", ".join(operations) if operations else "NONE")
        )
        if semantic.sensitivity is not DataSensitivity.PUBLIC:
            lines.append(f"  Sensitivity: {semantic.sensitivity.value}")
        if self.options.include_examples and semantic.example_values:
            examples = tuple(semantic.example_values)[
                : self.options.max_examples_per_column
            ]
            lines.append("  Example values (hints only): " + ", ".join(examples))
        for warning in semantic.interpretation_warnings:
            lines.append(f"  Warning: {warning}")
        return lines

    def _relationship_lines(
        self,
        query_space: ResolvedQuerySpace,
        profiled_space: ProfiledQuerySpace | None = None,
    ) -> list[str]:
        lines = ["", "Relationships:"]
        if not query_space.relationships:
            return lines + ["- <none>"]
        for relationship in sorted(
            query_space.relationships, key=lambda item: item.identity_key
        ):
            if profiled_space is not None:
                if not profiled_space.is_table_available(
                    relationship.source_table
                ) or not profiled_space.is_table_available(relationship.target_table):
                    continue
                src_caps = profiled_space.get_effective_capabilities(
                    relationship.source_table, relationship.source_column
                )
                tgt_caps = profiled_space.get_effective_capabilities(
                    relationship.target_table, relationship.target_column
                )
                if not src_caps.joinable or not tgt_caps.joinable:
                    continue

            source = query_space.get_table(relationship.source_table)
            target = query_space.get_table(relationship.target_table)
            source_name = source.semantic.entity_name or source.ref.table
            target_name = target.semantic.entity_name or target.ref.table
            lines.extend(
                [
                    (
                        f"- {'Strict' if relationship.strict else 'Semantic'}: "
                        f"{source_name}.{relationship.source_column} -> "
                        f"{target_name}.{relationship.target_column}"
                    ),
                    (
                        "  Physical join: "
                        f"{_quoted_table(source)}.{_quote(relationship.source_column)} = "
                        f"{_quoted_table(target)}.{_quote(relationship.target_column)}"
                    ),
                ]
            )
        return lines


def _quote(identifier: str) -> str:
    return "[" + identifier.replace("]", "]]") + "]"


def _quoted_table(table: ResolvedTable) -> str:
    return f"{_quote(table.ref.schema)}.{_quote(table.ref.table)}"


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"
