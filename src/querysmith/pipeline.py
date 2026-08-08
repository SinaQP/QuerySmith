"""Orchestration helpers for QuerySmith query generation and execution."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import replace
from typing import Literal, overload

from sqlalchemy import Engine, text

from querysmith.audit import (
    AuditEvent,
    AuditLogger,
    NullAuditLogger,
    generate_request_id,
)
from querysmith.context import ContextBuilder
from querysmith.introspector import SQLServerIntrospector, introspect_schema
from querysmith.llm import LLMClient, OpenAICompatibleClient, generate_sql
from querysmith.models import (
    AccessProfile,
    ProfiledQuerySpace,
    QuerySpace,
    QuerySpaceValidationError,
    ResolvedQuerySpace,
)
from querysmith.policy import AuthorizedQuery, PolicyEngine
from querysmith.profiles import AccessProfileResolver
from querysmith.resolver import CatalogResolver
from querysmith.sanitizer import ResultSanitizer, SanitizedResult
from querysmith.serializer import serialize_schema


def generate_query_in_space(
    question: str,
    query_space: ResolvedQuerySpace | ProfiledQuerySpace,
    client: LLMClient,
    *,
    access_profile: AccessProfile | str | None = None,
    runtime_context: Mapping[str, object] | None = None,
    audit_logger: AuditLogger | None = None,
    request_id: str | None = None,
) -> str:
    """Generate SQL using only metadata and tables in a QuerySpace or ProfiledQuerySpace."""

    return authorize_query_in_space(
        question,
        query_space,
        client,
        access_profile=access_profile,
        runtime_context=runtime_context,
        audit_logger=audit_logger,
        request_id=request_id,
    ).sql


def _validate_runtime_context_before_llm(
    profiled_space: ProfiledQuerySpace,
    runtime_context: Mapping[str, object] | None,
) -> None:
    """Pre-validate runtime context values and required keys before triggering LLM generation or execution."""

    from querysmith.policy import validate_runtime_context

    validate_runtime_context(profiled_space, runtime_context)


def authorize_query_in_space(
    question: str,
    query_space: ResolvedQuerySpace | ProfiledQuerySpace,
    client: LLMClient,
    *,
    access_profile: AccessProfile | str | None = None,
    runtime_context: Mapping[str, object] | None = None,
    policy_engine: PolicyEngine | None = None,
    audit_logger: AuditLogger | None = None,
    request_id: str | None = None,
) -> AuthorizedQuery:
    """Generate SQL and return only the final, policy-applied authorization result."""

    req_id = request_id or generate_request_id()
    logger = audit_logger or NullAuditLogger()

    if isinstance(query_space, ProfiledQuerySpace):
        profiled_space = query_space
    elif isinstance(query_space, ResolvedQuerySpace):
        profiled_space = AccessProfileResolver().resolve(query_space, access_profile)
    else:
        raise TypeError(
            "authorize_query_in_space requires a ResolvedQuerySpace or ProfiledQuerySpace."
        )

    prof_name = profiled_space.access_profile.name

    qs_name = getattr(profiled_space.resolved_query_space, "name", "QuerySpace")

    logger.emit(
        AuditEvent(
            request_id=req_id,
            event_type="query_received",
            query_space=qs_name,
            access_profile=prof_name,
            question=question,
        )
    )
    logger.emit(
        AuditEvent(
            request_id=req_id,
            event_type="profile_resolved",
            query_space=qs_name,
            access_profile=prof_name,
        )
    )

    _validate_runtime_context_before_llm(profiled_space, runtime_context)

    context_text = ContextBuilder().build(profiled_space)
    llm_start = time.perf_counter()
    generated_sql = generate_sql(question, context_text, client)
    llm_duration = (time.perf_counter() - llm_start) * 1000.0

    logger.emit(
        AuditEvent(
            request_id=req_id,
            event_type="sql_generated",
            query_space=qs_name,
            access_profile=prof_name,
            generated_sql=generated_sql,
            execution_duration_ms=llm_duration,
        )
    )

    auth_start = time.perf_counter()
    try:
        authorized = (policy_engine or PolicyEngine()).authorize_and_apply(
            generated_sql, profiled_space, runtime_context
        )
        auth_duration = (time.perf_counter() - auth_start) * 1000.0
        report = authorized.authorization
        logger.emit(
            AuditEvent(
                request_id=req_id,
                event_type="authorization_allowed",
                query_space=qs_name,
                access_profile=prof_name,
                generated_sql=generated_sql,
                authorized_sql=authorized.sql,
                parameter_names=tuple(authorized.parameters.keys()),
                tables_used=report.tables_used if report else (),
                columns_used=report.columns_used if report else {},
                injected_policies=authorized.applied_policies,
                applied_masks=report.applied_masks if report else (),
                hidden_columns=report.hidden_columns if report else (),
                authorization_allowed=True,
                execution_duration_ms=auth_duration,
            )
        )
        return authorized
    except Exception as error:
        auth_duration = (time.perf_counter() - auth_start) * 1000.0
        err_code = getattr(error, "code", None)
        err_code_str = (
            err_code.value
            if err_code is not None and hasattr(err_code, "value")
            else str(err_code)
            if err_code is not None
            else type(error).__name__
        )
        report = getattr(error, "report", None)
        logger.emit(
            AuditEvent(
                request_id=req_id,
                event_type="authorization_denied",
                query_space=qs_name,
                access_profile=prof_name,
                generated_sql=generated_sql,
                authorization_allowed=False,
                error_code=err_code_str,
                tables_used=report.tables_used if report else (),
                columns_used=report.columns_used if report else {},
                execution_duration_ms=auth_duration,
            )
        )
        raise


def generate_query(
    question: str,
    engine: Engine,
    client: LLMClient,
    schema: str = "dbo",
    *,
    query_space: QuerySpace | ResolvedQuerySpace | None = None,
    access_profile: AccessProfile | str | None = None,
    runtime_context: Mapping[str, object] | None = None,
    audit_logger: AuditLogger | None = None,
    request_id: str | None = None,
) -> str:
    """Generate safe SQL, retaining the original schema-based adapter."""

    if query_space is not None:
        resolved = resolve_query_space(query_space, engine=engine)
        return generate_query_in_space(
            question,
            resolved,
            client,
            access_profile=access_profile,
            runtime_context=runtime_context,
            audit_logger=audit_logger,
            request_id=request_id,
        )

    tables = introspect_schema(engine, schema=schema)
    if not tables:
        return generate_sql(question, serialize_schema(tables), client)
    return generate_query_in_space(
        question,
        QuerySpace.from_legacy_tables(tables),
        client,
        access_profile=access_profile,
        runtime_context=runtime_context,
        audit_logger=audit_logger,
        request_id=request_id,
    )


def execute_select(
    engine: Engine,
    sql: str,
    max_rows: int = 100,
    *,
    query_space: ResolvedQuerySpace | ProfiledQuerySpace | None = None,
    access_profile: AccessProfile | str | None = None,
    runtime_context: Mapping[str, object] | None = None,
    audit_logger: AuditLogger | None = None,
    request_id: str | None = None,
) -> SanitizedResult | list[dict[str, object]]:
    """Validate and execute a SELECT query with a conservative row limit."""

    if (
        not isinstance(max_rows, int)
        or isinstance(max_rows, bool)
        or max_rows <= 0
        or max_rows > 1000
    ):
        raise ValueError("max_rows must be an int between 1 and 1000.")

    if query_space is None:
        from querysmith.exceptions import MissingQuerySpaceError

        raise MissingQuerySpaceError(
            "execute_select requires a ResolvedQuerySpace or ProfiledQuerySpace. "
            "Direct raw SQL execution without an active QuerySpace is forbidden."
        )

    if isinstance(query_space, ProfiledQuerySpace):
        profiled_space = query_space
    elif isinstance(query_space, ResolvedQuerySpace):
        profiled_space = AccessProfileResolver().resolve(query_space, access_profile)
    else:
        raise TypeError(
            "execute_select requires a ResolvedQuerySpace or ProfiledQuerySpace."
        )

    effective_max_rows = min(max_rows, profiled_space.execution_policy.max_rows)
    effective_policy = replace(
        profiled_space.execution_policy, max_rows=effective_max_rows
    )
    effective_space = replace(profiled_space, execution_policy=effective_policy)
    authorized = PolicyEngine().authorize_and_apply(
        sql, effective_space, runtime_context
    )
    return execute_authorized_query(
        engine,
        authorized,
        effective_space,
        runtime_context=runtime_context,
        audit_logger=audit_logger,
        request_id=request_id,
    )


def execute_authorized_query(
    engine: Engine,
    authorized_query: AuthorizedQuery,
    query_space: ResolvedQuerySpace | ProfiledQuerySpace,
    *,
    access_profile: AccessProfile | str | None = None,
    runtime_context: Mapping[str, object] | None = None,
    sanitizer: ResultSanitizer | None = None,
    audit_logger: AuditLogger | None = None,
    request_id: str | None = None,
) -> SanitizedResult:
    """Execute only a final AuthorizedQuery under its resolved execution policy and return a SanitizedResult."""

    from querysmith.exceptions import QueryTimeoutError

    req_id = request_id or generate_request_id()
    logger = audit_logger or NullAuditLogger()

    if not isinstance(authorized_query, AuthorizedQuery):
        raise TypeError("execute_authorized_query requires an AuthorizedQuery.")

    if isinstance(query_space, ProfiledQuerySpace):
        profiled_space = query_space
    elif isinstance(query_space, ResolvedQuerySpace):
        profiled_space = AccessProfileResolver().resolve(query_space, access_profile)
    else:
        raise TypeError(
            "execute_authorized_query requires a ResolvedQuerySpace or ProfiledQuerySpace."
        )

    exec_policy = profiled_space.execution_policy
    if not exec_policy.allow_execution:
        raise QuerySpaceValidationError(
            "Execution is disabled by the active QuerySpace policy."
        )

    prof_name = profiled_space.access_profile.name

    qs_name = getattr(profiled_space.resolved_query_space, "name", "QuerySpace")

    logger.emit(
        AuditEvent(
            request_id=req_id,
            event_type="execution_started",
            query_space=qs_name,
            access_profile=prof_name,
            authorized_sql=authorized_query.sql,
            parameter_names=tuple(authorized_query.parameters.keys()),
        )
    )

    statement = text(authorized_query.sql)
    timeout = exec_policy.timeout_seconds
    start_t = time.perf_counter()
    try:
        with engine.connect() as connection:
            conn = (
                connection.execution_options(timeout=timeout)
                if hasattr(connection, "execution_options")
                else connection
            )
            if authorized_query.parameters:
                result = conn.execute(statement, dict(authorized_query.parameters))
            else:
                result = conn.execute(statement)

            max_fetch = exec_policy.max_rows + 1
            raw_rows: list[dict[str, object]] = []
            for row in result.mappings():
                raw_rows.append(dict(row))
                if len(raw_rows) >= max_fetch:
                    break
    except Exception as error:
        exec_duration = (time.perf_counter() - start_t) * 1000.0
        err_msg = str(error).casefold()
        err_code_str = (
            "EXECUTION_TIMEOUT"
            if (
                "timeout" in err_msg
                or "timed out" in err_msg
                or "canceling statement" in err_msg
                or "cancelled" in err_msg
            )
            else type(error).__name__
        )
        logger.emit(
            AuditEvent(
                request_id=req_id,
                event_type="execution_failed",
                query_space=qs_name,
                access_profile=prof_name,
                authorized_sql=authorized_query.sql,
                error_code=err_code_str,
                execution_duration_ms=exec_duration,
            )
        )
        if (
            "timeout" in err_msg
            or "timed out" in err_msg
            or "canceling statement" in err_msg
            or "cancelled" in err_msg
        ):
            raise QueryTimeoutError(
                f"Query execution timed out after {timeout} seconds."
            ) from error
        raise

    exec_duration = (time.perf_counter() - start_t) * 1000.0
    sanitized = (sanitizer or ResultSanitizer()).sanitize(
        authorized_query, raw_rows, profiled_space
    )

    logger.emit(
        AuditEvent(
            request_id=req_id,
            event_type="execution_succeeded",
            query_space=qs_name,
            access_profile=prof_name,
            authorized_sql=authorized_query.sql,
            execution_duration_ms=exec_duration,
            row_count=len(sanitized.rows),
            truncated=sanitized.truncated,
        )
    )

    return sanitized


@overload
def ask(
    question: str,
    *,
    schema: str | None = None,
    query_space: QuerySpace | ResolvedQuerySpace | None = None,
    access_profile: AccessProfile | str | None = None,
    runtime_context: Mapping[str, object] | None = None,
    engine: Engine | None = None,
    client: LLMClient | None = None,
    resolver: CatalogResolver | None = None,
    audit_logger: AuditLogger | None = None,
    request_id: str | None = None,
    execute: Literal[False] = False,
) -> str: ...


@overload
def ask(
    question: str,
    *,
    schema: str | None = None,
    query_space: QuerySpace | ResolvedQuerySpace | None = None,
    access_profile: AccessProfile | str | None = None,
    runtime_context: Mapping[str, object] | None = None,
    engine: Engine | None = None,
    client: LLMClient | None = None,
    resolver: CatalogResolver | None = None,
    audit_logger: AuditLogger | None = None,
    request_id: str | None = None,
    execute: Literal[True],
) -> SanitizedResult: ...


def ask(
    question: str,
    *,
    schema: str | None = None,
    query_space: QuerySpace | ResolvedQuerySpace | None = None,
    access_profile: AccessProfile | str | None = None,
    runtime_context: Mapping[str, object] | None = None,
    engine: Engine | None = None,
    client: LLMClient | None = None,
    resolver: CatalogResolver | None = None,
    audit_logger: AuditLogger | None = None,
    request_id: str | None = None,
    execute: bool = False,
) -> str | SanitizedResult:
    """Generate, and optionally execute, SQL in a schema or QuerySpace."""

    if (schema is None) == (query_space is None):
        raise QuerySpaceValidationError("Provide exactly one of schema or query_space.")

    req_id = request_id or generate_request_id()

    resolved_engine = engine
    resolved_space: ResolvedQuerySpace
    if query_space is None:
        resolved_engine = _resolve_engine(engine)
        resolved_space = QuerySpace.from_schema(
            schema or "",
            engine=resolved_engine,
        )
    else:
        if isinstance(query_space, ResolvedQuerySpace):
            resolved_space = query_space
        else:
            if resolver is None:
                resolved_engine = _resolve_engine(engine)
                resolver = CatalogResolver(SQLServerIntrospector(resolved_engine))
            resolved_space = resolver.resolve(query_space)

    resolved_space.validate()
    profiled_space = AccessProfileResolver().resolve(resolved_space, access_profile)

    if execute:
        if not profiled_space.execution_policy.allow_execution:
            raise QuerySpaceValidationError(
                "Execution is disabled by the active QuerySpace policy."
            )
        resolved_engine = _resolve_engine(resolved_engine)

    resolved_client = client or OpenAICompatibleClient()
    authorized = authorize_query_in_space(
        question,
        profiled_space,
        resolved_client,
        runtime_context=runtime_context,
        audit_logger=audit_logger,
        request_id=req_id,
    )
    if not execute:
        return authorized.sql

    assert resolved_engine is not None
    return execute_authorized_query(
        resolved_engine,
        authorized,
        profiled_space,
        runtime_context=runtime_context,
        audit_logger=audit_logger,
        request_id=req_id,
    )


def resolve_query_space(
    query_space: QuerySpace | ResolvedQuerySpace,
    *,
    engine: Engine | None = None,
    resolver: CatalogResolver | None = None,
) -> ResolvedQuerySpace:
    """Resolve developer intent once, or validate an already resolved space."""

    if isinstance(query_space, ResolvedQuerySpace):
        query_space.validate()
        return query_space
    if resolver is None:
        resolver = CatalogResolver(SQLServerIntrospector(_resolve_engine(engine)))
    return resolver.resolve(query_space)


def _resolve_engine(engine: Engine | None) -> Engine:
    if engine is not None:
        return engine

    from querysmith.config import load_config
    from querysmith.db import make_engine

    return make_engine(load_config())
