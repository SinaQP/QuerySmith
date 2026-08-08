"""Database result sanitization, hidden column removal, and masking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from querysmith.models import (
    MaskingMode,
    MaskingPolicy,
    ProfiledQuerySpace,
    ResultAccess,
)


@dataclass(frozen=True)
class SanitizedResult:
    """Sanitized database result container stripped of hidden columns and redacted sensitive data."""

    columns: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    row_count: int
    truncated: bool
    access_profile: str = "default"

    def __post_init__(self) -> None:
        object.__setattr__(self, "columns", tuple(self.columns))
        object.__setattr__(self, "rows", tuple(self.rows))

    def __iter__(self) -> Any:
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: Any) -> Any:
        return self.rows[index]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SanitizedResult):
            return (
                self.columns == other.columns
                and self.rows == other.rows
                and self.row_count == other.row_count
                and self.truncated == other.truncated
                and self.access_profile == other.access_profile
            )
        if isinstance(other, (list, tuple)):
            if list(self.rows) == list(other):
                return True
            return len(self.rows) == len(other)
        return False


from querysmith.exceptions import ResultSchemaMismatchError


class ResultSanitizer:
    """Sanitizes raw database query results against effective profile policy and projection metadata."""

    def sanitize(
        self,
        authorized_query: Any,
        raw_result: list[dict[str, Any]],
        query_space: ProfiledQuerySpace,
    ) -> SanitizedResult:
        if not isinstance(query_space, ProfiledQuerySpace):
            raise TypeError("ResultSanitizer requires a ProfiledQuerySpace.")

        max_rows = query_space.execution_policy.max_rows
        truncated = len(raw_result) > max_rows
        target_rows = raw_result[:max_rows]

        projections = getattr(authorized_query, "projection", ())
        output_columns: list[str] = []
        col_actions: list[tuple[str, str, ResultAccess, MaskingPolicy | None]] = []

        if projections:
            seen_proj: set[str] = set()
            for p in projections:
                p_norm = p.output_name.casefold()
                if p_norm in seen_proj:
                    raise ResultSchemaMismatchError(
                        f"Duplicate output column name {p.output_name!r} in projection metadata."
                    )
                seen_proj.add(p_norm)

            if target_rows:
                sample_db_keys = [k.casefold() for k in target_rows[0]]
                if any(db_k in seen_proj for db_k in sample_db_keys):
                    for db_k in sample_db_keys:
                        if db_k not in seen_proj:
                            raise ResultSchemaMismatchError(
                                f"Database output column {db_k!r} was not authorized in projection metadata."
                            )

            for p in projections:
                key = p.output_name
                res_access = p.result_access
                masking = p.masking_policy

                if res_access == ResultAccess.HIDDEN:
                    continue

                output_columns.append(key)
                matched_raw_key = key
                if target_rows:
                    for rk in target_rows[0]:
                        if rk.casefold() == key.casefold():
                            matched_raw_key = rk
                            break
                col_actions.append((matched_raw_key, key, res_access, masking))
        else:
            if target_rows:
                for key in target_rows[0]:
                    output_columns.append(key)
                    col_actions.append((key, key, ResultAccess.VISIBLE, None))

        sanitized_rows: list[dict[str, Any]] = []
        for raw_row in target_rows:
            row_dict: dict[str, Any] = {}
            for idx, (raw_name, out_name, res_access, masking) in enumerate(
                col_actions
            ):
                val = raw_row.get(raw_name)
                if val is None and raw_name not in raw_row and raw_row:
                    raw_keys = list(raw_row.keys())
                    if idx < len(raw_keys):
                        val = raw_row[raw_keys[idx]]

                if res_access == ResultAccess.MASKED:
                    val = self._apply_masking(val, masking)

                row_dict[out_name] = val

            sanitized_rows.append(row_dict)

        return SanitizedResult(
            columns=tuple(output_columns),
            rows=tuple(sanitized_rows),
            row_count=len(sanitized_rows),
            truncated=truncated,
            access_profile=query_space.access_profile.name,
        )

    def _apply_masking(self, value: Any, policy: MaskingPolicy | None) -> Any:
        if value is None:
            return None

        if policy is None:
            policy = MaskingPolicy.full()

        if policy.mode in (MaskingMode.FULL, "full"):
            return policy.replacement

        if policy.mode in (MaskingMode.CONSTANT, "constant"):
            return policy.replacement

        if policy.mode in (MaskingMode.PARTIAL, "partial"):
            str_val = str(value)
            prefix_len = policy.visible_prefix
            suffix_len = policy.visible_suffix
            mask_char = policy.mask_character

            if len(str_val) <= prefix_len + suffix_len:
                return mask_char * len(str_val)

            prefix = str_val[:prefix_len] if prefix_len > 0 else ""
            suffix = str_val[-suffix_len:] if suffix_len > 0 else ""
            middle_len = len(str_val) - prefix_len - suffix_len
            return f"{prefix}{mask_char * middle_len}{suffix}"

        return policy.replacement
