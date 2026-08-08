"""Mandatory policy injection and final SQL authorization orchestration."""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import cast

from sqlglot import exp
from sqlglot.optimizer.scope import Scope, traverse_scope

from querysmith.authorization import (
    AuthorizationReport,
    ColumnUsage,
    FinalAuthorizationError,
    MandatoryPolicyError,
    ParsedSQL,
    PolicyInjectionError,
    RelationshipUsage,
    SQLAuthorizationError,
    SQLAuthorizer,
    SQLParser,
)
from querysmith.exceptions import (
    ConflictingMandatoryFilterError,
    FinalSQLValidationError,
    InvalidRuntimeContextValueError,
    MissingRuntimeContextError,
    OuterJoinRewriteError,
)
from querysmith.models import (
    FilterOperator,
    MandatoryFilterPolicy,
    ProfiledQuerySpace,
    ProjectionColumn,
    RequiredFilter,
    ResolvedQuerySpace,
    TableRef,
)


@dataclass(frozen=True)
class AuthorizedQuery:
    """Immutable final SQL and audit metadata safe for the execution boundary."""

    original_sql: str
    sql: str
    parameters: Mapping[str, object] = field(default_factory=dict)
    applied_policies: tuple[str, ...] = ()
    authorization: AuthorizationReport | None = None
    is_authorized: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        if self.authorization is None:
            raise FinalAuthorizationError(
                "AuthorizedQuery requires a successful authorization report."
            )
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        object.__setattr__(self, "applied_policies", tuple(self.applied_policies))

    @property
    def referenced_tables(self) -> tuple[TableRef, ...]:
        assert self.authorization is not None
        return self.authorization.referenced_tables

    @property
    def referenced_columns(self) -> tuple[ColumnUsage, ...]:
        assert self.authorization is not None
        return self.authorization.referenced_columns

    @property
    def relationships(self) -> tuple[RelationshipUsage, ...]:
        assert self.authorization is not None
        return self.authorization.relationships

    @property
    def projection(self) -> tuple[ProjectionColumn, ...]:
        assert self.authorization is not None
        return self.authorization.projection


@dataclass(frozen=True)
class InjectionResult:
    """Internal immutable result of AST policy injection."""

    expression: exp.Query
    parameters: Mapping[str, object]
    applied_policies: tuple[str, ...]
    trusted_columns: frozenset[tuple[tuple[str, str], str]]


def validate_runtime_context(
    query_space: ResolvedQuerySpace | ProfiledQuerySpace,
    runtime_context: Mapping[str, object] | None,
) -> None:
    """Pre-validate runtime context keys and values against active row policies."""

    res_space = (
        query_space.resolved_query_space
        if isinstance(query_space, ProfiledQuerySpace)
        else query_space
    )
    exec_policy = query_space.execution_policy

    all_filters: list[
        tuple[TableRef | None, MandatoryFilterPolicy | RequiredFilter]
    ] = [(pol.table, pol) for pol in exec_policy.mandatory_filters]
    for tbl in res_space.tables:
        for req_f in tbl.required_filters:
            all_filters.append((tbl.ref, req_f))

    ctx = dict(runtime_context or {})

    for _, policy in all_filters:
        if isinstance(policy, RequiredFilter) and policy.value_from_context is not None:
            key = policy.value_from_context
            if key not in ctx:
                raise MissingRuntimeContextError(
                    f"Required runtime context key {key!r} is missing."
                )
            val = ctx[key]
            _validate_context_value(key, val, policy.operator)

    for k, v in ctx.items():
        if callable(v) or hasattr(v, "sql"):
            raise InvalidRuntimeContextValueError(
                f"Invalid runtime context value for key {k!r}: raw SQL fragments, callables, and complex objects are forbidden."
            )


def _validate_context_value(
    key: str, val: object, operator: FilterOperator | str
) -> None:
    if callable(val) or hasattr(val, "sql"):
        raise InvalidRuntimeContextValueError(
            f"Invalid runtime context value for key {key!r}: raw SQL fragments, callables, and complex objects are forbidden."
        )

    if hasattr(val, "__dict__") and not isinstance(
        val, (int, float, str, bool, bytes, datetime.date, datetime.datetime, uuid.UUID)
    ):
        raise InvalidRuntimeContextValueError(
            f"Invalid runtime context value for key {key!r}: complex objects are forbidden."
        )

    op = (
        FilterOperator(operator)
        if not isinstance(operator, FilterOperator)
        else operator
    )

    if op is FilterOperator.IN:
        if isinstance(val, (str, bytes)) or not isinstance(
            val, (list, tuple, set, frozenset)
        ):
            raise InvalidRuntimeContextValueError(
                f"Invalid runtime context value for key {key!r}: IN operator requires a non-empty collection."
            )
        if len(val) == 0:
            raise InvalidRuntimeContextValueError(
                f"Invalid runtime context value for key {key!r}: IN filter collection cannot be empty."
            )
        if len(val) > 1000:
            raise InvalidRuntimeContextValueError(
                f"Invalid runtime context value for key {key!r}: IN filter collection exceeds maximum limit of 1000 items."
            )
        for item in val:
            if (
                callable(item)
                or hasattr(item, "sql")
                or (
                    hasattr(item, "__dict__")
                    and not isinstance(
                        item,
                        (
                            int,
                            float,
                            str,
                            bool,
                            bytes,
                            datetime.date,
                            datetime.datetime,
                            uuid.UUID,
                        ),
                    )
                )
            ):
                raise InvalidRuntimeContextValueError(
                    f"Invalid collection element in runtime context key {key!r}: complex objects are forbidden."
                )
    else:
        if isinstance(val, (list, tuple, set, frozenset, dict)):
            raise InvalidRuntimeContextValueError(
                f"Invalid runtime context value for key {key!r}: scalar operator requires a scalar value, got collection."
            )


class PolicyInjector:
    """Apply typed mandatory filters and a T-SQL TOP limit to a copied AST."""

    def apply(
        self,
        parsed: ParsedSQL,
        query_space: ResolvedQuerySpace | ProfiledQuerySpace,
        runtime_context: Mapping[str, object] | None = None,
    ) -> InjectionResult:
        validate_runtime_context(query_space, runtime_context)
        expression = cast(exp.Query, parsed.expression.copy())
        parameters: dict[str, object] = {}
        applied: list[str] = []
        trusted: set[tuple[tuple[str, str], str]] = set()
        occurrence = 0

        res_space = (
            query_space.resolved_query_space
            if isinstance(query_space, ProfiledQuerySpace)
            else query_space
        )
        exec_policy = query_space.execution_policy

        all_filters: list[
            tuple[TableRef | None, MandatoryFilterPolicy | RequiredFilter]
        ] = [(pol.table, pol) for pol in exec_policy.mandatory_filters]
        for tbl in res_space.tables:
            for req_f in tbl.required_filters:
                all_filters.append((tbl.ref, req_f))

        for scope in traverse_scope(expression):
            if not isinstance(scope.expression, exp.Select):
                continue
            for alias, (_, source) in scope.selected_sources.items():
                if not isinstance(source, exp.Table):
                    continue
                ref = self._table_ref(source, res_space)
                if ref is None:
                    continue
                for policy_index, (pol_table, policy) in enumerate(all_filters):
                    target_table = pol_table or ref
                    if target_table != ref:
                        continue

                    target = self._injection_target(scope, source)
                    if target is None:
                        raise OuterJoinRewriteError(
                            f"Mandatory policy for {ref.full_name} cannot be injected "
                            "without changing join semantics."
                        )
                    container, location = target
                    policy_name = (
                        f"mandatory_filter:{target_table.full_name}.{policy.column}"
                    )
                    trusted.add((target_table.identity_key, policy.column.casefold()))

                    pol_value: object = None
                    if isinstance(policy, RequiredFilter):
                        if policy.value_from_context is not None:
                            ctx = runtime_context or {}
                            if policy.value_from_context not in ctx:
                                raise MissingRuntimeContextError(
                                    f"Required runtime context key {policy.value_from_context!r} is missing."
                                )
                            pol_value = ctx[policy.value_from_context]
                        else:
                            pol_value = policy.value
                    else:
                        pol_value = policy.value

                    m_policy = MandatoryFilterPolicy(
                        table=target_table,
                        column=policy.column,
                        operator=policy.operator,
                        value=pol_value,
                    )

                    self._check_contradictions(container, alias, m_policy)

                    if self._contains_policy_conjunct(container, alias, m_policy):
                        if policy_name not in applied:
                            applied.append(policy_name)
                        continue
                    parameter_name = f"qs_policy_{policy_index}_{occurrence}"
                    occurrence += 1
                    predicate, new_params = self._predicate(
                        alias, m_policy, parameter_name
                    )
                    parameters.update(new_params)
                    self._append_predicate(container, location, predicate)
                    if policy_name not in applied:
                        applied.append(policy_name)
        if self._apply_row_limit(expression, exec_policy.max_rows):
            applied.append(f"row_limit:{exec_policy.max_rows}")
        return InjectionResult(
            expression,
            MappingProxyType(parameters),
            tuple(applied),
            frozenset(trusted),
        )

    @staticmethod
    def _table_ref(
        table: exp.Table, query_space: ResolvedQuerySpace
    ) -> TableRef | None:
        if table.db:
            ref = TableRef(table.db, table.name)
            return ref if ref in query_space.table_refs else None
        matches = [
            ref
            for ref in query_space.table_refs
            if ref.table.casefold() == table.name.casefold()
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            from querysmith.exceptions import AmbiguousPolicyTargetError

            raise AmbiguousPolicyTargetError(
                f"Policy injection target table {table.name!r} is ambiguous."
            )
        return None

    @staticmethod
    def _injection_target(
        scope: Scope, table: exp.Table
    ) -> tuple[exp.Expression, str] | None:
        if isinstance(scope.expression, exp.Select) and any(
            (join.side or "").upper() in {"RIGHT", "FULL"}
            for join in scope.expression.args.get("joins") or ()
        ):
            side = next(
                (join.side or "").upper()
                for join in scope.expression.args.get("joins") or ()
                if (join.side or "").upper() in {"RIGHT", "FULL"}
            )
            raise OuterJoinRewriteError(
                f"Mandatory policy for {table.name!r} cannot be injected into a {side} JOIN "
                "without changing join semantics."
            )
        parent = table.parent
        if isinstance(parent, exp.Join):
            side = (parent.side or "").upper()
            if side == "LEFT":
                if parent.args.get("on") is None:
                    raise OuterJoinRewriteError(
                        f"Left join missing ON clause for policy target {table.name!r}."
                    )
                return parent, "on"
            if side in {"RIGHT", "FULL"}:
                raise OuterJoinRewriteError(
                    f"Mandatory policy for {table.name!r} cannot be injected into a {side} JOIN "
                    "without changing join semantics."
                )
        if not isinstance(scope.expression, exp.Select):
            return None
        return scope.expression, "where"

    @staticmethod
    def _append_predicate(
        container: exp.Expression,
        location: str,
        predicate: exp.Expression,
    ) -> None:
        if location == "on":
            existing = container.args.get("on")
            if existing is None:
                raise PolicyInjectionError("Join policy target has no ON predicate.")
            container.set(
                "on",
                exp.and_(
                    cast(exp.Expression, existing).copy(),
                    predicate,
                    wrap=True,
                ),
            )
            return
        where = container.args.get("where")
        if isinstance(where, exp.Where):
            predicate = cast(
                exp.Expression,
                exp.and_(where.this.copy(), predicate, wrap=True),
            )
        container.set("where", exp.Where(this=predicate))

    @staticmethod
    def _predicate(
        alias: str,
        policy: MandatoryFilterPolicy,
        parameter_name: str,
    ) -> tuple[exp.Expression, dict[str, object]]:
        column = exp.column(policy.column, table=alias)
        if policy.operator is FilterOperator.IN:
            assert isinstance(policy.value, (list, tuple, set, frozenset))
            val_list = list(policy.value)
            placeholders = [
                exp.Placeholder(this=f"{parameter_name}_p{i}")
                for i in range(len(val_list))
            ]
            new_params = {
                f"{parameter_name}_p{i}": val for i, val in enumerate(val_list)
            }
            return exp.In(this=column, expressions=placeholders), new_params

        if policy.value is None:
            is_null = exp.Is(this=column, expression=exp.Null())
            if policy.operator is FilterOperator.EQ:
                return is_null, {}
            if policy.operator is FilterOperator.NE:
                return exp.Not(this=is_null), {}
            raise MandatoryPolicyError(
                "Null mandatory filters require equality or inequality."
            )
        value = exp.Placeholder(this=parameter_name)
        constructors: dict[FilterOperator, type[exp.Binary]] = {
            FilterOperator.EQ: exp.EQ,
            FilterOperator.NE: exp.NEQ,
            FilterOperator.GT: exp.GT,
            FilterOperator.GTE: exp.GTE,
            FilterOperator.LT: exp.LT,
            FilterOperator.LTE: exp.LTE,
        }
        assert isinstance(policy.operator, FilterOperator)
        expr = cast(
            exp.Expression,
            constructors[policy.operator](this=column, expression=value),
        )
        return expr, {parameter_name: policy.value}

    @staticmethod
    def _check_contradictions(
        container: exp.Expression,
        alias: str,
        policy: MandatoryFilterPolicy,
    ) -> None:
        if isinstance(container, exp.Join):
            root = container.args.get("on")
        else:
            where = container.args.get("where")
            root = where.this if isinstance(where, exp.Where) else None
        if not isinstance(root, exp.Expression):
            return

        for term in PolicyInjector._and_terms(root):
            if (
                policy.value is not None
                and policy.operator in (FilterOperator.EQ, FilterOperator.IN)
                and isinstance(term, exp.Is)
                and isinstance(term.expression, exp.Null)
                and PolicyInjector._is_policy_column(term.this, alias, policy)
            ):
                raise ConflictingMandatoryFilterError(
                    f"Query condition IS NULL contradicts mandatory policy for {alias}.{policy.column}."
                )

            if policy.operator is FilterOperator.EQ and policy.value is not None:
                if (
                    isinstance(term, exp.NEQ)
                    and PolicyInjector._is_policy_column(term.left, alias, policy)
                    and PolicyInjector._literal_matches(term.right, policy.value)
                ):
                    raise ConflictingMandatoryFilterError(
                        f"Query condition {alias}.{policy.column} != {policy.value!r} contradicts mandatory policy."
                    )
                if isinstance(term, exp.EQ) and PolicyInjector._is_policy_column(
                    term.left, alias, policy
                ):
                    right = term.right
                    if isinstance(
                        right, exp.Literal
                    ) and not PolicyInjector._literal_matches(right, policy.value):
                        raise ConflictingMandatoryFilterError(
                            f"Query condition {alias}.{policy.column} = {right.this!r} contradicts mandatory policy value {policy.value!r}."
                        )

            if (
                policy.operator is FilterOperator.IN
                and isinstance(policy.value, (list, tuple, set, frozenset))
                and isinstance(term, exp.EQ)
                and PolicyInjector._is_policy_column(term.left, alias, policy)
            ):
                pol_str_set = {str(v).casefold() for v in policy.value}
                if (
                    isinstance(term.right, exp.Literal)
                    and str(term.right.this).casefold() not in pol_str_set
                ):
                    raise ConflictingMandatoryFilterError(
                        f"Query condition {alias}.{policy.column} = {term.right.this!r} is outside mandatory IN policy values."
                    )

    def _contains_policy_conjunct(
        self,
        container: exp.Expression,
        alias: str,
        policy: MandatoryFilterPolicy,
    ) -> bool:
        if isinstance(container, exp.Join):
            root = container.args.get("on")
        else:
            where = container.args.get("where")
            root = where.this if isinstance(where, exp.Where) else None
        if not isinstance(root, exp.Expression):
            return False
        return any(
            self._matches_policy(term, alias, policy) for term in self._and_terms(root)
        )

    @staticmethod
    def _matches_policy(
        expression: exp.Expression,
        alias: str,
        policy: MandatoryFilterPolicy,
    ) -> bool:
        candidate = expression
        if policy.value is None and policy.operator is FilterOperator.NE:
            if not isinstance(candidate, exp.Not):
                return False
            candidate = cast(exp.Expression, candidate.this)
        if policy.value is None:
            if not isinstance(candidate, exp.Is):
                return False
            return PolicyInjector._is_policy_column(
                candidate.this, alias, policy
            ) and isinstance(candidate.expression, exp.Null)

        if policy.operator is FilterOperator.IN:
            if not isinstance(candidate, exp.In):
                return False
            if not PolicyInjector._is_policy_column(candidate.this, alias, policy):
                return False
            if all(
                isinstance(item, exp.Placeholder) and item.name.startswith("qs_policy_")
                for item in candidate.expressions
            ):
                return True
            if isinstance(policy.value, (list, tuple, set, frozenset)):
                val_list = list(policy.value)
                if len(candidate.expressions) != len(val_list):
                    return False
                return all(
                    PolicyInjector._literal_matches(expr, val)
                    for expr, val in zip(candidate.expressions, val_list, strict=False)
                )
            return False

        operators: dict[FilterOperator, type[exp.Binary]] = {
            FilterOperator.EQ: exp.EQ,
            FilterOperator.NE: exp.NEQ,
            FilterOperator.GT: exp.GT,
            FilterOperator.GTE: exp.GTE,
            FilterOperator.LT: exp.LT,
            FilterOperator.LTE: exp.LTE,
        }
        assert isinstance(policy.operator, FilterOperator)
        if not isinstance(candidate, operators[policy.operator]):
            return False
        if not PolicyInjector._is_policy_column(candidate.left, alias, policy):
            return False
        right = candidate.right
        if isinstance(right, exp.Placeholder):
            return right.name.startswith("qs_policy_")
        return PolicyInjector._literal_matches(right, policy.value)

    @staticmethod
    def _is_policy_column(
        expression: object,
        alias: str,
        policy: MandatoryFilterPolicy,
    ) -> bool:
        return (
            isinstance(expression, exp.Column)
            and expression.table.casefold() == alias.casefold()
            and expression.name.casefold() == policy.column.casefold()
        )

    @staticmethod
    def _literal_matches(expression: object, value: object) -> bool:
        if isinstance(value, bool) and isinstance(expression, exp.Boolean):
            return bool(expression.this) is value
        if isinstance(value, bool) and isinstance(expression, exp.Literal):
            return expression.this in ({"1"} if value else {"0"})
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not isinstance(expression, exp.Literal) or not expression.is_number:
                return False
            try:
                return float(expression.this) == float(value)
            except ValueError:
                return False
        return (
            isinstance(value, str)
            and isinstance(expression, exp.Literal)
            and expression.is_string
            and expression.this == value
        )

    @staticmethod
    def _apply_row_limit(expression: exp.Query, max_rows: int) -> bool:
        if PolicyInjector._is_scalar_aggregate(expression):
            return False
        limit = expression.args.get("limit")
        if isinstance(limit, exp.Limit) and isinstance(limit.expression, exp.Literal):
            try:
                current = int(limit.expression.this)
            except ValueError:
                current = max_rows + 1
            if current <= max_rows:
                return False
        expression.set("limit", exp.Limit(expression=exp.Literal.number(max_rows)))
        return True

    @staticmethod
    def _is_scalar_aggregate(expression: exp.Query) -> bool:
        if not isinstance(expression, exp.Select) or expression.args.get("group"):
            return False
        if not expression.expressions:
            return False
        for projection in expression.expressions:
            target = (
                projection.this if isinstance(projection, exp.Alias) else projection
            )
            if not isinstance(target, (exp.AggFunc, exp.Literal)):
                return False
        return any(
            isinstance(
                projection.this if isinstance(projection, exp.Alias) else projection,
                exp.AggFunc,
            )
            for projection in expression.expressions
        )

    @staticmethod
    def _and_terms(expression: exp.Expression) -> tuple[exp.Expression, ...]:
        if isinstance(expression, exp.Paren):
            return PolicyInjector._and_terms(cast(exp.Expression, expression.this))
        if isinstance(expression, exp.And):
            return PolicyInjector._and_terms(
                cast(exp.Expression, expression.left)
            ) + PolicyInjector._and_terms(cast(exp.Expression, expression.right))
        return (expression,)


class PolicyEngine:
    """Authorize, inject typed policies, and re-authorize final SQL."""

    def __init__(
        self,
        parser: SQLParser | None = None,
        authorizer: SQLAuthorizer | None = None,
        injector: PolicyInjector | None = None,
    ) -> None:
        self.parser = parser or SQLParser()
        self.authorizer = authorizer or SQLAuthorizer()
        self.injector = injector or PolicyInjector()

    def authorize_and_apply(
        self,
        sql: str,
        query_space: ResolvedQuerySpace | ProfiledQuerySpace,
        runtime_context: Mapping[str, object] | None = None,
    ) -> AuthorizedQuery:

        validate_runtime_context(query_space, runtime_context)
        parsed = self.parser.parse(sql)
        initial = self.authorizer.authorize(parsed, query_space)
        try:
            injection = self.injector.apply(parsed, query_space, runtime_context)
        except TypeError:
            injection = self.injector.apply(parsed, query_space)

        final_sql = injection.expression.sql(dialect="tsql")
        try:
            reparsed = self.parser.parse(final_sql)
            final = self.authorizer.authorize(
                reparsed,
                query_space,
                trusted_policy_columns=injection.trusted_columns,
                trusted_derived_projection_star=isinstance(
                    injection.expression, exp.SetOperation
                ),
            )
        except SQLAuthorizationError as error:
            raise FinalSQLValidationError(
                "Final SQL failed authorization after mandatory policy injection."
            ) from error
        if set(final.referenced_tables) != set(initial.referenced_tables):
            raise FinalSQLValidationError(
                "Policy injection changed the authorized query's physical tables."
            )
        initial_columns = {
            (usage.table.identity_key, usage.column.casefold())
            for usage in initial.referenced_columns
        }
        final_columns = {
            (usage.table.identity_key, usage.column.casefold())
            for usage in final.referenced_columns
        }
        if final_columns != initial_columns | set(injection.trusted_columns):
            raise FinalSQLValidationError(
                "Policy injection changed physical columns beyond mandatory policy targets."
            )
        return AuthorizedQuery(
            original_sql=parsed.original_sql,
            sql=final_sql,
            parameters=injection.parameters,
            applied_policies=injection.applied_policies,
            authorization=final,
        )
