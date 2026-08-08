"""Tests for deterministic, capability-rich QuerySpace context."""

from querysmith.context import ContextBuilder, ContextBuilderOptions
from querysmith.models import (
    ColumnSpec,
    ResolvedQuerySpace,
    TableRef,
    TableSpec,
)
from querysmith.semantic import (
    BusinessRule,
    ColumnCapabilities,
    DataSensitivity,
    SemanticType,
)
from querysmith.serializer import serialize_query_space


def _space() -> ResolvedQuerySpace:
    ref = TableRef("Sales", "Order")
    return ResolvedQuerySpace(
        [
            TableSpec(
                ref,
                [
                    ColumnSpec(
                        "Total",
                        "decimal",
                        False,
                        alias="order_value",
                        description="Final payable amount",
                        synonyms=("مبلغ سفارش",),
                        semantic_type=SemanticType.CURRENCY,
                        unit="IRR",
                        example_values=("125000",),
                        capabilities=ColumnCapabilities(joinable=False),
                        interpretation_warnings=("Includes tax",),
                        sensitivity=DataSensitivity.INTERNAL,
                        precision=12,
                        scale=2,
                    ),
                    ColumnSpec("OrderId", "int", False, primary_key=True),
                ],
                alias="orders",
                description="Commercial orders",
                synonyms=("سفارش‌ها",),
                business_rules=(BusinessRule("Ignore cancelled orders", ref),),
                interpretation_warnings=("Dates use Tehran time",),
            )
        ]
    )


def test_context_distinguishes_semantic_and_physical_metadata() -> None:
    context = ContextBuilder().build(_space())

    assert "ENTITY: orders" in context
    assert "Physical table: Sales.Order (SQL: [Sales].[Order])" in context
    assert "Physical column: [Total] (decimal(12,2), NOT NULL)" in context
    assert "Semantic name: order_value" in context
    assert "Semantic type: currency" in context
    assert "Unit: IRR" in context
    assert "Allowed operations: SELECT, FILTER, SORT, GROUP, AGGREGATE" in context
    assert "Sensitivity: internal" in context
    assert "Example values (hints only): 125000" in context
    assert "Business rules (advisory):" in context
    assert "Warning: Includes tax" in context


def test_context_is_deterministic_and_serializer_is_compatibility_wrapper() -> None:
    space = _space()

    first = ContextBuilder().build(space)
    second = ContextBuilder().build(space)

    assert first == second == serialize_query_space(space)
    assert first.index("OrderId") < first.index("Total")


def test_context_options_can_suppress_examples() -> None:
    context = ContextBuilder(ContextBuilderOptions(include_examples=False)).build(
        _space()
    )

    assert "125000" not in context
