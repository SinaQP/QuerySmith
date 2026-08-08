"""Structured and secure audit logging system for QuerySmith."""

from __future__ import annotations

import datetime
import logging
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

import sqlglot
from sqlglot import exp

logger = logging.getLogger("querysmith.audit")


def generate_request_id() -> str:
    """Generate a secure unique request identifier."""
    return f"req-{uuid.uuid4().hex}"


def redact_sql_literals(sql: str) -> str:
    """Redact string and numeric literal constants from SQL text for safe audit logging."""
    if not sql or not sql.strip():
        return sql
    try:
        parsed = sqlglot.parse_one(sql, read="tsql")

        def _transform(node: exp.Expression) -> exp.Expression:
            if isinstance(node, exp.Literal):
                if node.is_string:
                    return exp.Literal.string("[REDACTED]")
                if node.is_number:
                    return exp.Literal.number(0)
            return node

        redacted = parsed.transform(_transform)
        return redacted.sql(dialect="tsql")
    except Exception:  # noqa: BLE001
        # Defensive regex fallback if parsing fails
        sql_no_str = re.sub(r"'(?:''|[^'])*'", "'[REDACTED]'", sql)
        sql_no_num = re.sub(r"\b\d+\b", "0", sql_no_str)
        return sql_no_num


@dataclass(frozen=True)
class AuditLoggingPolicy:
    """Policy governing security and redaction boundaries for audit logs."""

    log_question: bool = False
    log_generated_sql: bool = True
    log_authorized_sql: bool = True
    log_parameter_values: bool = False
    log_raw_results: bool = False
    max_question_length: int = 200


@dataclass(frozen=True)
class AuditEvent:
    """Immutable structured security audit log record."""

    request_id: str
    event_type: str
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat()
    )
    query_space: str | None = None
    access_profile: str | None = None
    question: str | None = None
    generated_sql: str | None = None
    authorized_sql: str | None = None
    parameter_names: tuple[str, ...] = ()
    tables_used: tuple[str, ...] = ()
    columns_used: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    injected_policies: tuple[str, ...] = ()
    applied_masks: tuple[str, ...] = ()
    hidden_columns: tuple[str, ...] = ()
    authorization_allowed: bool | None = None
    error_code: str | None = None
    execution_duration_ms: float | None = None
    row_count: int | None = None
    truncated: bool | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a clean JSON-serializable dictionary representation."""
        data: dict[str, Any] = {
            "request_id": self.request_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
        }
        if self.query_space is not None:
            data["query_space"] = self.query_space
        if self.access_profile is not None:
            data["access_profile"] = self.access_profile
        if self.question is not None:
            data["question"] = self.question
        if self.generated_sql is not None:
            data["generated_sql"] = self.generated_sql
        if self.authorized_sql is not None:
            data["authorized_sql"] = self.authorized_sql
        if self.parameter_names:
            data["parameter_names"] = list(self.parameter_names)
        if self.tables_used:
            data["tables_used"] = list(self.tables_used)
        if self.columns_used:
            data["columns_used"] = {k: list(v) for k, v in self.columns_used.items()}
        if self.injected_policies:
            data["injected_policies"] = list(self.injected_policies)
        if self.applied_masks:
            data["applied_masks"] = list(self.applied_masks)
        if self.hidden_columns:
            data["hidden_columns"] = list(self.hidden_columns)
        if self.authorization_allowed is not None:
            data["authorization_allowed"] = self.authorization_allowed
        if self.error_code is not None:
            data["error_code"] = self.error_code
        if self.execution_duration_ms is not None:
            data["execution_duration_ms"] = self.execution_duration_ms
        if self.row_count is not None:
            data["row_count"] = self.row_count
        if self.truncated is not None:
            data["truncated"] = self.truncated
        if self.extra:
            data["extra"] = dict(self.extra)
        return data


class AuditLogger(Protocol):
    """Protocol interface for audit logging backends."""

    def emit(self, event: AuditEvent) -> None:
        """Emit one audit event."""
        ...


class PythonLoggingAuditLogger:
    """Audit logger backend emitting structured records through Python logging."""

    def __init__(
        self,
        logger_instance: logging.Logger | None = None,
        policy: AuditLoggingPolicy | None = None,
    ) -> None:
        self.logger = logger_instance or logger
        self.policy = policy or AuditLoggingPolicy()

    def emit(self, event: AuditEvent) -> None:
        try:
            sanitized = self._sanitize_event(event)
            self.logger.info("AUDIT_EVENT: %s", sanitized.to_dict())
        except Exception as err:  # noqa: BLE001
            # Audit logging failure must never fail authorization or crash caller
            self.logger.warning("Failed to emit audit event safely: %s", err)

    def _sanitize_event(self, event: AuditEvent) -> AuditEvent:
        question = event.question
        if not self.policy.log_question:
            question = None
        elif question and len(question) > self.policy.max_question_length:
            question = question[: self.policy.max_question_length] + "..."

        gen_sql = (
            redact_sql_literals(event.generated_sql)
            if self.policy.log_generated_sql and event.generated_sql
            else None
        )
        auth_sql = (
            redact_sql_literals(event.authorized_sql)
            if self.policy.log_authorized_sql and event.authorized_sql
            else None
        )

        return AuditEvent(
            request_id=event.request_id,
            event_type=event.event_type,
            timestamp=event.timestamp,
            query_space=event.query_space,
            access_profile=event.access_profile,
            question=question,
            generated_sql=gen_sql,
            authorized_sql=auth_sql,
            parameter_names=event.parameter_names,
            tables_used=event.tables_used,
            columns_used=event.columns_used,
            injected_policies=event.injected_policies,
            applied_masks=event.applied_masks,
            hidden_columns=event.hidden_columns,
            authorization_allowed=event.authorization_allowed,
            error_code=event.error_code,
            execution_duration_ms=event.execution_duration_ms,
            row_count=event.row_count,
            truncated=event.truncated,
            extra=event.extra,
        )


class NullAuditLogger:
    """No-op audit logger backend."""

    def emit(self, event: AuditEvent) -> None:
        pass
