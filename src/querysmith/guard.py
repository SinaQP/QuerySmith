"""Application-level validation for generated SQL Server SELECT queries."""

from __future__ import annotations

import re


class UnsafeQueryError(ValueError):
    """Raised when SQL text does not pass the read-only safety guard."""


_DANGEROUS_KEYWORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "MERGE",
    "EXEC",
    "EXECUTE",
    "GRANT",
    "REVOKE",
    "DENY",
    "BACKUP",
    "RESTORE",
    "DBCC",
    "USE",
)

_RISKY_ACCESS_KEYWORDS = (
    "OPENROWSET",
    "OPENDATASOURCE",
    "BULK",
)

_DANGEROUS_KEYWORD_PATTERN = re.compile(
    rf"\b({'|'.join(_DANGEROUS_KEYWORDS)})\b",
    re.IGNORECASE,
)
_RISKY_ACCESS_PATTERN = re.compile(
    rf"\b({'|'.join(_RISKY_ACCESS_KEYWORDS)})\b",
    re.IGNORECASE,
)
_SELECT_INTO_PATTERN = re.compile(r"\bSELECT\b[\s\S]*?\bINTO\b", re.IGNORECASE)
_OUTPUT_INTO_PATTERN = re.compile(r"\bOUTPUT\b[\s\S]*?\bINTO\b", re.IGNORECASE)
_PROCEDURE_PATTERN = re.compile(r"\b(?:xp|sp)_", re.IGNORECASE)
_LINKED_SERVER_PATTERN = re.compile(
    r"(?:\[[^\]]+\]|\b[A-Za-z_][\w$]*\b)\s*\.\s*"
    r"(?:\[[^\]]+\]|\b[A-Za-z_][\w$]*\b)\s*\.\s*"
    r"(?:\[[^\]]+\]|\b[A-Za-z_][\w$]*\b)\s*\.\s*"
    r"(?:\[[^\]]+\]|\b[A-Za-z_][\w$]*\b)"
)


def validate_safe_select(sql: str) -> str:
    """Validate that SQL text is a single conservative read-only SELECT query.

    Returns the stripped SQL with one optional trailing semicolon removed.
    Raises UnsafeQueryError when the query is empty or potentially unsafe.
    """

    stripped_sql = sql.strip()
    if not stripped_sql:
        raise UnsafeQueryError("SQL query is empty.")

    if "--" in stripped_sql or "/*" in stripped_sql or "*/" in stripped_sql:
        raise UnsafeQueryError("SQL comments are not allowed.")

    query = _remove_optional_trailing_semicolon(stripped_sql)
    if ";" in query:
        raise UnsafeQueryError("Multiple SQL statements are not allowed.")

    normalized = _normalize_sql(query)
    if not normalized.startswith(("SELECT ", "WITH ")):
        raise UnsafeQueryError("Only SELECT or WITH SELECT queries are allowed.")

    if normalized.startswith("WITH ") and not re.search(r"\bSELECT\b", normalized):
        raise UnsafeQueryError("WITH queries must contain SELECT.")

    if _DANGEROUS_KEYWORD_PATTERN.search(normalized):
        raise UnsafeQueryError("SQL query contains a dangerous keyword.")

    if _SELECT_INTO_PATTERN.search(normalized):
        raise UnsafeQueryError("SELECT INTO is not allowed.")

    if _OUTPUT_INTO_PATTERN.search(normalized):
        raise UnsafeQueryError("OUTPUT INTO is not allowed.")

    if _RISKY_ACCESS_PATTERN.search(normalized):
        raise UnsafeQueryError("Risky external data access is not allowed.")

    if _PROCEDURE_PATTERN.search(normalized):
        raise UnsafeQueryError("SQL Server procedure access is not allowed.")

    if _LINKED_SERVER_PATTERN.search(normalized):
        raise UnsafeQueryError("Linked-server style object names are not allowed.")

    return query


def _remove_optional_trailing_semicolon(sql: str) -> str:
    if sql.endswith(";"):
        return sql[:-1].strip()

    return sql


def _normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().upper()
