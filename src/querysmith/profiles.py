"""Access profile resolution and validation for QuerySmith."""

from __future__ import annotations

from types import MappingProxyType

from querysmith.exceptions import (
    MissingAccessProfileError,
    ProfileConflictError,
    UnknownAccessProfileError,
)
from querysmith.models import (
    AccessProfile,
    ColumnAccess,
    ColumnAccessLevel,
    ColumnCapabilities,
    MaskingPolicy,
    ProfiledQuerySpace,
    RequiredFilter,
    ResolvedQuerySpace,
    ResolvedTable,
    ResultAccess,
    TableAccess,
    TableRef,
)


class AccessProfileResolver:
    """Resolves an active AccessProfile against a ResolvedQuerySpace."""

    def resolve(
        self,
        query_space: ResolvedQuerySpace,
        access_profile: AccessProfile | str | None,
    ) -> ProfiledQuerySpace:
        if not isinstance(query_space, ResolvedQuerySpace):
            raise TypeError("resolve requires a ResolvedQuerySpace.")

        query_space.validate()
        declared_profiles = self._collect_declared_profiles(query_space)

        if declared_profiles:
            if access_profile is None:
                raise MissingAccessProfileError(
                    "Access profile is required for this profile-aware QuerySpace."
                )
            profile_obj = (
                access_profile
                if isinstance(access_profile, AccessProfile)
                else AccessProfile(access_profile)
            )
            if profile_obj.identity_key not in declared_profiles:
                raise UnknownAccessProfileError(
                    f"Access profile {profile_obj.name!r} is not defined in QuerySpace."
                )
        else:
            profile_obj = (
                access_profile
                if isinstance(access_profile, AccessProfile)
                else AccessProfile(
                    access_profile if access_profile is not None else "default"
                )
            )

        table_access: dict[TableRef, TableAccess] = {}
        column_access: dict[tuple[TableRef, str], ColumnAccess] = {}
        effective_capabilities: dict[tuple[TableRef, str], ColumnCapabilities] = {}
        result_access: dict[tuple[TableRef, str], ResultAccess] = {}
        masking_policies: dict[tuple[TableRef, str], MaskingPolicy] = {}

        for table in query_space.tables:
            ref = table.ref
            dev_table = self._find_developer_table(query_space, ref)
            t_access = TableAccess(available=True)
            if (
                dev_table is not None
                and dev_table.profiles
                and profile_obj.identity_key in dev_table.profiles
            ):
                t_access = dev_table.profiles[profile_obj.identity_key]

            table_access[ref] = t_access

            for col in table.columns:
                col_key = (ref, col.name.casefold())
                dev_col = (
                    dev_table.get_column(col.name) if dev_table is not None else None
                )

                c_access: ColumnAccess | None = None
                if (
                    dev_col is not None
                    and dev_col.profiles
                    and profile_obj.identity_key in dev_col.profiles
                ):
                    c_access = dev_col.profiles[profile_obj.identity_key]

                if c_access is None:
                    if col.access is ColumnAccessLevel.DENIED:
                        c_access = ColumnAccess.deny()
                    elif col.access is ColumnAccessLevel.POLICY_ONLY:
                        c_access = ColumnAccess(
                            selectable=False,
                            filterable=True,
                            sortable=False,
                            groupable=False,
                            aggregatable=False,
                            joinable=False,
                            result_access=ResultAccess.HIDDEN,
                        )
                    else:
                        col_caps = col.capabilities or ColumnCapabilities()
                        c_access = ColumnAccess(
                            selectable=col_caps.selectable,
                            filterable=col_caps.filterable,
                            sortable=col_caps.sortable,
                            groupable=col_caps.groupable,
                            aggregatable=col_caps.aggregatable,
                            joinable=col_caps.joinable,
                            result_access=ResultAccess.VISIBLE,
                            capabilities=col_caps,
                        )

                if (
                    c_access.result_access == ResultAccess.VISIBLE
                    and not c_access.selectable
                ):
                    raise ProfileConflictError(
                        f"Column {ref.full_name}.{col.name} under profile {profile_obj.name!r} "
                        "has result_access=VISIBLE but selectable=False."
                    )

                if (
                    c_access.result_access == ResultAccess.MASKED
                    and not c_access.selectable
                ):
                    raise ProfileConflictError(
                        f"Column {ref.full_name}.{col.name} under profile {profile_obj.name!r} "
                        "has result_access=MASKED but selectable=False."
                    )

                eff_caps = c_access.capabilities or ColumnCapabilities(
                    selectable=c_access.selectable,
                    filterable=c_access.filterable,
                    sortable=c_access.sortable,
                    groupable=c_access.groupable,
                    aggregatable=c_access.aggregatable,
                    joinable=c_access.joinable,
                )

                masking = c_access.masking
                if c_access.result_access == ResultAccess.MASKED and masking is None:
                    masking = MaskingPolicy.full()

                column_access[col_key] = c_access
                effective_capabilities[col_key] = eff_caps
                result_access[col_key] = ResultAccess(c_access.result_access)
                if masking is not None:
                    masking_policies[col_key] = masking

        req_filters: list[RequiredFilter] = []
        for table in query_space.tables:
            dev_table = self._find_developer_table(query_space, table.ref)
            if dev_table is not None and dev_table.required_filters:
                for rf in dev_table.required_filters:
                    rf_table = rf.table or table.ref
                    req_filters.append(
                        RequiredFilter(
                            table=rf_table,
                            column=rf.column,
                            operator=rf.operator,
                            value_from_context=rf.value_from_context,
                            value=rf.value,
                        )
                    )

        return ProfiledQuerySpace(
            access_profile=profile_obj,
            resolved_query_space=query_space,
            table_access=MappingProxyType(table_access),
            column_access=MappingProxyType(column_access),
            effective_capabilities=MappingProxyType(effective_capabilities),
            result_access=MappingProxyType(result_access),
            masking_policies=MappingProxyType(masking_policies),
            required_filters=tuple(req_filters),
            execution_policy=query_space.execution_policy,
        )

    @staticmethod
    def _collect_declared_profiles(query_space: ResolvedQuerySpace) -> set[str]:
        profiles: set[str] = set()
        for t in query_space.tables:
            if t.profiles:
                profiles.update(t.profiles.keys())
            for c in t.columns:
                if c.profiles:
                    profiles.update(c.profiles.keys())
        return profiles

    @staticmethod
    def _find_developer_table(
        query_space: ResolvedQuerySpace, ref: TableRef
    ) -> ResolvedTable | None:
        for t in query_space.tables:
            if isinstance(t, ResolvedTable) and t.ref == ref:
                return t
        return None
