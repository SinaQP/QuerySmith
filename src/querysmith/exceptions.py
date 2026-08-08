"""Custom exception hierarchy for QuerySmith security, profiles, and execution safety."""

from enum import Enum
from typing import Any

from querysmith.models import QuerySpaceError


class AuthorizationErrorCode(str, Enum):
    """Stable security error codes for authorization violations."""

    TABLE_NOT_ALLOWED = "TABLE_NOT_ALLOWED"
    COLUMN_SELECT_NOT_ALLOWED = "COLUMN_SELECT_NOT_ALLOWED"
    COLUMN_FILTER_NOT_ALLOWED = "COLUMN_FILTER_NOT_ALLOWED"
    COLUMN_GROUP_NOT_ALLOWED = "COLUMN_GROUP_NOT_ALLOWED"
    COLUMN_SORT_NOT_ALLOWED = "COLUMN_SORT_NOT_ALLOWED"
    COLUMN_AGGREGATE_NOT_ALLOWED = "COLUMN_AGGREGATE_NOT_ALLOWED"
    COLUMN_JOIN_NOT_ALLOWED = "COLUMN_JOIN_NOT_ALLOWED"
    SELECT_STAR_NOT_ALLOWED = "SELECT_STAR_NOT_ALLOWED"
    AMBIGUOUS_COLUMN = "AMBIGUOUS_COLUMN"
    RELATIONSHIP_NOT_ALLOWED = "RELATIONSHIP_NOT_ALLOWED"
    ACCESS_PROFILE_NOT_ALLOWED = "ACCESS_PROFILE_NOT_ALLOWED"
    MANDATORY_FILTER_MISSING = "MANDATORY_FILTER_MISSING"
    MANDATORY_FILTER_CONFLICT = "MANDATORY_FILTER_CONFLICT"
    POLICY_BYPASS_ATTEMPT = "POLICY_BYPASS_ATTEMPT"
    HIDDEN_COLUMN_EXPOSURE = "HIDDEN_COLUMN_EXPOSURE"
    MASKING_BYPASS_ATTEMPT = "MASKING_BYPASS_ATTEMPT"
    UNSUPPORTED_QUERY_SHAPE = "UNSUPPORTED_QUERY_SHAPE"


class AccessProfileError(QuerySpaceError):
    """Base exception for access profile configuration and resolution errors."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message)
        self.code = code or AuthorizationErrorCode.ACCESS_PROFILE_NOT_ALLOWED
        self.report = report


class UnknownAccessProfileError(AccessProfileError):
    """Raised when a requested access profile is not defined in the QuerySpace."""


class MissingAccessProfileError(AccessProfileError):
    """Raised when a profile-aware QuerySpace is invoked without an access profile."""


class ProfileConflictError(AccessProfileError):
    """Raised when access profile rules or capabilities are internally conflicting."""


class ProfileResolutionError(AccessProfileError):
    """Raised when resolving effective profile permissions fails."""


class ResultPolicyError(QuerySpaceError):
    """Base exception for database result sanitization and output schema failures."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message)
        self.code = code or AuthorizationErrorCode.HIDDEN_COLUMN_EXPOSURE
        self.report = report


class ResultSchemaMismatchError(ResultPolicyError):
    """Raised when database output columns do not match the authorized AST projection."""


class HiddenColumnExposureError(ResultPolicyError):
    """Raised when a hidden column is detected in unauthorized output projection."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code=code or AuthorizationErrorCode.HIDDEN_COLUMN_EXPOSURE,
            report=report,
        )


class MaskingPolicyError(ResultPolicyError):
    """Raised when a masking policy is invalid or cannot be safely applied."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code=code or AuthorizationErrorCode.MASKING_BYPASS_ATTEMPT,
            report=report,
        )


class UnsupportedMaskedExpressionError(ResultPolicyError):
    """Raised when SQL expressions attempt to transform or bypass a masked column."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code=code or AuthorizationErrorCode.MASKING_BYPASS_ATTEMPT,
            report=report,
        )


class ExecutionSafetyError(QuerySpaceError):
    """Base exception for query shape, join limits, and runtime execution constraints."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message)
        self.code = code or AuthorizationErrorCode.UNSUPPORTED_QUERY_SHAPE
        self.report = report


class QueryShapeNotAllowedError(ExecutionSafetyError):
    """Raised when a query shape violates execution policy rules."""


class TooManyJoinsError(QueryShapeNotAllowedError):
    """Raised when a query exceeds the maximum allowed join count."""


class SubqueryNotAllowedError(QueryShapeNotAllowedError):
    """Raised when subqueries are disabled by execution policy."""


class CTENotAllowedError(QueryShapeNotAllowedError):
    """Raised when CTEs are disabled by execution policy."""


class CrossJoinNotAllowedError(QueryShapeNotAllowedError):
    """Raised when cross joins or cartesian products are disabled by execution policy."""


class SelectStarNotAllowedError(QueryShapeNotAllowedError):
    """Raised when projection wildcards are disabled or invalid."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code=code or AuthorizationErrorCode.SELECT_STAR_NOT_ALLOWED,
            report=report,
        )


class QueryTimeoutError(ExecutionSafetyError):
    """Raised when SQL execution times out on the database server."""


class ResultRowLimitError(ExecutionSafetyError):
    """Raised when result set limits are violated."""


class MissingQuerySpaceError(ExecutionSafetyError):
    """Raised when a query execution pipeline is invoked without a required QuerySpace."""


class RuntimePolicyError(QuerySpaceError):
    """Base exception for runtime context and mandatory row-level policy injection."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message)
        self.code = code or AuthorizationErrorCode.MANDATORY_FILTER_MISSING
        self.report = report


class RowLevelPolicyError(RuntimePolicyError):
    """Base exception for row-level policy failures."""


class MissingRuntimeContextError(RowLevelPolicyError):
    """Raised when a required runtime context key is missing."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code=code or AuthorizationErrorCode.MANDATORY_FILTER_MISSING,
            report=report,
        )


class InvalidRuntimeContextValueError(RowLevelPolicyError):
    """Raised when a runtime context value is invalid or unsafe."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code=code or AuthorizationErrorCode.MANDATORY_FILTER_MISSING,
            report=report,
        )


class RequiredFilterTargetError(RowLevelPolicyError):
    """Raised when a required filter target cannot be resolved."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code=code or AuthorizationErrorCode.MANDATORY_FILTER_MISSING,
            report=report,
        )


class RowPolicyBypassError(RowLevelPolicyError):
    """Raised when a query attempts to bypass or neutralize a row policy."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code=code or AuthorizationErrorCode.POLICY_BYPASS_ATTEMPT,
            report=report,
        )


class RequiredFilterInjectionError(RuntimePolicyError):
    """Raised when a mandatory row-level filter cannot be injected safely."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code=code or AuthorizationErrorCode.MANDATORY_FILTER_MISSING,
            report=report,
        )


class RuntimeParameterConflictError(RuntimePolicyError):
    """Raised when runtime parameter names collide."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code=code or AuthorizationErrorCode.MANDATORY_FILTER_CONFLICT,
            report=report,
        )


class SQLRewriteError(RuntimePolicyError):
    """Base exception for AST-based SQL rewrite failures."""


class SQLAuthorizationError(QuerySpaceError, ValueError):
    """Base class for deterministic SQL authorization failures."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        table: str | None = None,
        column: str | None = None,
        operation: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.report = report
        self.table = table
        self.column = column
        self.operation = operation


class MandatoryPolicyError(SQLAuthorizationError, RowLevelPolicyError):
    """Raised when a typed mandatory policy is invalid or cannot be applied."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code=code or AuthorizationErrorCode.MANDATORY_FILTER_CONFLICT,
            report=report,
            **kwargs,
        )


class ConflictingMandatoryFilterError(MandatoryPolicyError):
    """Raised when a user predicate conflicts with a mandatory row-level policy."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code=code or AuthorizationErrorCode.MANDATORY_FILTER_CONFLICT,
            report=report,
            **kwargs,
        )


class PolicyInjectionError(MandatoryPolicyError, SQLRewriteError):
    """Raised when an AST policy rewrite cannot be performed safely."""

    def __init__(
        self,
        message: str,
        code: AuthorizationErrorCode | str | None = None,
        report: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code=code or AuthorizationErrorCode.POLICY_BYPASS_ATTEMPT,
            report=report,
            **kwargs,
        )


class FinalAuthorizationError(SQLAuthorizationError):
    """Raised when rewritten SQL fails its second authorization pass."""


class UnsupportedRewriteShapeError(SQLRewriteError):
    """Raised when a query AST shape is not supported for safe rewriting."""


class AliasResolutionError(SQLRewriteError):
    """Raised when a table alias cannot be resolved during AST rewriting."""


class OuterJoinRewriteError(PolicyInjectionError):
    """Raised when an outer join cannot be safely rewritten with row policy."""


class AmbiguousPolicyTargetError(SQLRewriteError):
    """Raised when a policy target table or alias is ambiguous in AST rewriting."""


class FinalSQLValidationError(SQLRewriteError, FinalAuthorizationError):
    """Raised when rewritten SQL fails final authorization or re-parsing."""
