"""Backward-compatible façade over AST-based SQL authorization."""

from querysmith.authorization import (
    AmbiguousColumnError,
    ColumnOperationNotAllowedError,
    FinalAuthorizationError,
    MandatoryPolicyError,
    MultipleStatementError,
    PolicyInjectionError,
    RelationshipViolationError,
    SelectStarNotAllowedError,
    SQLAuthorizationError,
    SQLAuthorizer,
    SQLParseError,
    SQLParser,
    UnauthorizedColumnError,
    UnauthorizedJoinError,
    UnauthorizedTableError,
    UnsafeQueryError,
    UnsupportedStatementError,
)
from querysmith.models import ResolvedQuerySpace

__all__ = [
    "AmbiguousColumnError",
    "ColumnOperationNotAllowedError",
    "FinalAuthorizationError",
    "MandatoryPolicyError",
    "MultipleStatementError",
    "PolicyInjectionError",
    "RelationshipViolationError",
    "SQLAuthorizationError",
    "SQLParseError",
    "SelectStarNotAllowedError",
    "UnauthorizedColumnError",
    "UnauthorizedJoinError",
    "UnauthorizedTableError",
    "UnsafeQueryError",
    "UnsupportedStatementError",
    "validate_safe_select",
]


def validate_safe_select(
    sql: str,
    query_space: ResolvedQuerySpace | None = None,
) -> str:
    """Parse one read-only T-SQL query and optionally authorize its QuerySpace use."""

    parsed = SQLParser().parse(sql)
    if query_space is not None:
        SQLAuthorizer().authorize(parsed, query_space)
    return parsed.original_sql
