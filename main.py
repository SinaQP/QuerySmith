"""QuerySmith v0.2.0 — Interactive Real-Database Playground.

Demonstrates Natural Language SQL generation, AST authorization, security policy
enforcement, column masking, and live query execution against SQL Server / Database
using official QuerySmith domain models.

Usage:
    python main.py
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine, text

from querysmith import (
    AuditLoggingPolicy,
    AuthorizedQuery,
    CatalogResolver,
    ColumnAccess,
    ColumnAccessLevel,
    ColumnCapabilities,
    ColumnSpec,
    ExecutionPolicy,
    FilterOperator,
    MaskingPolicy,
    OpenAICompatibleClient,
    PolicyEngine,
    PythonLoggingAuditLogger,
    QuerySpace,
    RelationshipSpec,
    RequiredFilter,
    ResolvedQuerySpace,
    ResultAccess,
    SQLServerIntrospector,
    TableAccess,
    TableRef,
    TableSpec,
    authorize_query_in_space,
    execute_authorized_query,
    load_config,
    make_engine,
)
from querysmith.semantic import SemanticType

# Environment variable for database connection
DATABASE_URL_ENV = "QUERYSMITH_DATABASE_URL"


@dataclass
class DemoState:
    """State harness for interactive REPL playground."""

    access_profile: str = "analyst"
    execute_queries: bool = True
    engine: Engine | None = None
    resolved_space: ResolvedQuerySpace | None = None
    llm_client: OpenAICompatibleClient | None = None
    last_prepared: AuthorizedQuery | None = None
    last_error: Exception | None = None


# Configure UTF-8 output encoding for Windows terminal compatibility
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# =============================================================================
# 1. QUERYSPACE DECLARATION (UPM & COR SCHEMAS)
# =============================================================================
def build_query_space() -> QuerySpace:
    """Build the official QuerySpace for UPM (User Management) and Cor (Core municipal) tables."""
    tables = [
        # 1. UPM.Users
        TableSpec(
            ref=TableRef("UPM", "Users"),
            description=(
                "System application user accounts. Each row represents an account that can use/login to the application. "
                "IMPORTANT: A system user is not the same as a citizen/person in Cor.Persons. "
                "Use this entity when the question refers to: user / users, کاربر / کاربران, system account, login, "
                "username / نام کاربری, account status, user roles, user unit. Do not confuse system users with Cor.Persons."
            ),
            synonyms=[
                "کاربر",
                "کاربر سیستم",
                "یوزر",
                "حساب کاربری",
                "استفادهکننده سیستم",
                "نام کاربری",
                "user",
                "system user",
                "application user",
                "account",
                "user account",
                "login user",
            ],
            columns=[
                ColumnSpec(
                    "Id",
                    semantic_type=SemanticType.IDENTIFIER,
                    primary_key=True,
                    capabilities=ColumnCapabilities(
                        selectable=True,
                        filterable=True,
                        joinable=True,
                        sortable=True,
                        groupable=True,
                    ),
                ),
                ColumnSpec(
                    "FirstName",
                    semantic_type=SemanticType.TEXT,
                    description="First name of the system user. نام کاربر سیستم.",
                    synonyms=["نام", "اسم", "نام کاربر", "first name", "user first name"],
                    capabilities=ColumnCapabilities(
                        selectable=True,
                        filterable=True,
                        sortable=True,
                        groupable=True,
                    ),
                ),
                ColumnSpec(
                    "LastName",
                    semantic_type=SemanticType.TEXT,
                    description="Last name/family name of the system user. نام خانوادگی کاربر سیستم.",
                    synonyms=[
                        "نام خانوادگی",
                        "فامیلی",
                        "last name",
                        "family name",
                        "surname",
                    ],
                    capabilities=ColumnCapabilities(
                        selectable=True,
                        filterable=True,
                        sortable=True,
                        groupable=True,
                    ),
                ),
                ColumnSpec(
                    "UserName",
                    semantic_type=SemanticType.TEXT,
                    description="Login username of the system user. نام کاربری برای ورود به سیستم.",
                    synonyms=["نام کاربری", "یوزرنیم", "username", "login name"],
                    capabilities=ColumnCapabilities(
                        selectable=True, filterable=True, sortable=True
                    ),
                ),
                ColumnSpec(
                    "Email",
                    semantic_type=SemanticType.EMAIL,
                    description="Email address of system user.",
                    profiles={
                        "public": ColumnAccess.deny(),
                        "analyst": ColumnAccess(
                            selectable=True, filterable=True, result_access=ResultAccess.HIDDEN
                        ),
                        "internal": ColumnAccess.allow(),
                    },
                ),
                ColumnSpec(
                    "PhoneNumber",
                    semantic_type=SemanticType.PHONE,
                    description="Phone number of system user.",
                    profiles={
                        "public": ColumnAccess.deny(),
                        "analyst": ColumnAccess(
                            selectable=False, filterable=False, result_access=ResultAccess.HIDDEN
                        ),
                        "internal": ColumnAccess(
                            selectable=True,
                            filterable=False,
                            result_access=ResultAccess.MASKED,
                            masking=MaskingPolicy.partial(visible_prefix=0, visible_suffix=4),
                        ),
                    },
                ),
                ColumnSpec(
                    "PasswordHash",
                    allowed=False,
                    access=ColumnAccessLevel.DENIED,
                    profiles={
                        "public": ColumnAccess.deny(),
                        "analyst": ColumnAccess.deny(),
                        "internal": ColumnAccess.deny(),
                    },
                    description="Forbidden security field.",
                ),
                ColumnSpec(
                    "SecurityStamp",
                    allowed=False,
                    access=ColumnAccessLevel.DENIED,
                    profiles={
                        "public": ColumnAccess.deny(),
                        "analyst": ColumnAccess.deny(),
                        "internal": ColumnAccess.deny(),
                    },
                    description="Forbidden security field.",
                ),
                ColumnSpec(
                    "Lock",
                    semantic_type=SemanticType.BOOLEAN,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "ForcePasswordChange",
                    semantic_type=SemanticType.BOOLEAN,
                    capabilities=ColumnCapabilities(selectable=True),
                ),
                ColumnSpec(
                    "UnitId",
                    semantic_type=SemanticType.IDENTIFIER,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "CreatedByUserId",
                    semantic_type=SemanticType.IDENTIFIER,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "ModifiedByUserId",
                    semantic_type=SemanticType.IDENTIFIER,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "IsDeleted",
                    semantic_type=SemanticType.BOOLEAN,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "EmailConfirmed",
                    semantic_type=SemanticType.BOOLEAN,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "PhoneNumberConfirmed",
                    semantic_type=SemanticType.BOOLEAN,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "TwoFactorEnabled",
                    semantic_type=SemanticType.BOOLEAN,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "LockCounter",
                    profiles={
                        "public": ColumnAccess.deny(),
                        "analyst": ColumnAccess.deny(),
                        "internal": ColumnAccess(selectable=True),
                    },
                ),
                ColumnSpec(
                    "PrimaryLockCounter",
                    profiles={
                        "public": ColumnAccess.deny(),
                        "analyst": ColumnAccess.deny(),
                        "internal": ColumnAccess(selectable=True),
                    },
                ),
                ColumnSpec(
                    "LockoutEndDateUtc",
                    profiles={
                        "public": ColumnAccess.deny(),
                        "analyst": ColumnAccess.deny(),
                        "internal": ColumnAccess(selectable=True),
                    },
                ),
                ColumnSpec(
                    "LockoutEnabled",
                    semantic_type=SemanticType.BOOLEAN,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "AccessFailedCount",
                    profiles={
                        "public": ColumnAccess.deny(),
                        "analyst": ColumnAccess.deny(),
                        "internal": ColumnAccess(selectable=True),
                    },
                ),
                ColumnSpec(
                    "CreationDateTime",
                    semantic_type=SemanticType.DATETIME,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, sortable=True),
                ),
                ColumnSpec(
                    "ModificationDateTime",
                    semantic_type=SemanticType.DATETIME,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, sortable=True),
                ),
                ColumnSpec(
                    "BillDisplayName",
                    semantic_type=SemanticType.TEXT,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
            ],
            required_filters=[
                RequiredFilter(column="IsDeleted", operator=FilterOperator.EQ, value=0)
            ],
            profiles={
                "public": TableAccess(available=True),
                "analyst": TableAccess(available=True),
                "internal": TableAccess(available=True),
            },
        ),
        # 2. UPM.Roles
        TableSpec(
            ref=TableRef("UPM", "Roles"),
            description="Application roles assigned to users. نقشهای کاربران در سیستم.",
            synonyms=["role", "roles", "نقش", "نقش کاربر", "سطح نقش"],
            columns=[
                ColumnSpec(
                    "Id",
                    semantic_type=SemanticType.IDENTIFIER,
                    primary_key=True,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "Name",
                    semantic_type=SemanticType.TEXT,
                    description="Role title/name.",
                    synonyms=["نام نقش", "عنوان نقش", "role name", "role title"],
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, sortable=True),
                ),
                ColumnSpec(
                    "Descript",
                    semantic_type=SemanticType.TEXT,
                    description="Role description.",
                    synonyms=["توضیحات نقش", "شرح نقش"],
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "Premitive",
                    semantic_type=SemanticType.BOOLEAN,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "IsDeleted",
                    semantic_type=SemanticType.BOOLEAN,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "Discriminator",
                    semantic_type=SemanticType.TEXT,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
            ],
            required_filters=[
                RequiredFilter(column="IsDeleted", operator=FilterOperator.EQ, value=0)
            ],
            profiles={
                "public": TableAccess(available=True),
                "analyst": TableAccess(available=True),
                "internal": TableAccess(available=True),
            },
        ),
        # 3. UPM.UserRoles
        TableSpec(
            ref=TableRef("UPM", "UserRoles"),
            description="Bridge table linking system users to application roles.",
            synonyms=["user roles", "نقش‌های کاربر"],
            columns=[
                ColumnSpec(
                    "UserId",
                    semantic_type=SemanticType.IDENTIFIER,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "RoleId",
                    semantic_type=SemanticType.IDENTIFIER,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
            ],
            profiles={
                "public": TableAccess(available=True),
                "analyst": TableAccess(available=True),
                "internal": TableAccess(available=True),
            },
        ),
        # 4. UPM.UserClaims
        TableSpec(
            ref=TableRef("UPM", "UserClaims"),
            description="Claims assigned to an application user.",
            columns=[
                ColumnSpec(
                    "Id",
                    semantic_type=SemanticType.IDENTIFIER,
                    primary_key=True,
                    capabilities=ColumnCapabilities(selectable=True, joinable=True),
                ),
                ColumnSpec(
                    "UserId",
                    semantic_type=SemanticType.IDENTIFIER,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "ClaimType",
                    semantic_type=SemanticType.TEXT,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "ClaimValue",
                    semantic_type=SemanticType.TEXT,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
            ],
            profiles={
                "public": TableAccess(available=True),
                "analyst": TableAccess(available=True),
                "internal": TableAccess(available=True),
            },
        ),
        # 5. UPM.UserLog
        TableSpec(
            ref=TableRef("UPM", "UserLog"),
            description="Activity/audit history of application users. سوابق فعالیت کاربران سیستم.",
            synonyms=[
                "user log",
                "user logs",
                "user activity",
                "لاگ کاربر",
                "سوابق فعالیت کاربر",
                "فعالیت کاربر",
            ],
            columns=[
                ColumnSpec(
                    "Id",
                    semantic_type=SemanticType.IDENTIFIER,
                    primary_key=True,
                    capabilities=ColumnCapabilities(selectable=True, joinable=True),
                ),
                ColumnSpec(
                    "UserId",
                    semantic_type=SemanticType.IDENTIFIER,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "UserActivityTypeId",
                    semantic_type=SemanticType.IDENTIFIER,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "CreationDateTime",
                    description="Creation timestamp stored as text in UPM.UserLog.",
                    semantic_type=SemanticType.TEXT,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, sortable=True),
                ),
                ColumnSpec(
                    "IpAddress",
                    semantic_type=SemanticType.TEXT,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "DeviceType",
                    semantic_type=SemanticType.TEXT,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "Details",
                    semantic_type=SemanticType.TEXT,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
            ],
            profiles={
                "public": TableAccess(available=True),
                "analyst": TableAccess(available=True),
                "internal": TableAccess(available=True),
            },
        ),
        # 6. UPM.UserActivityType
        TableSpec(
            ref=TableRef("UPM", "UserActivityType"),
            description="Classification/type of a user activity.",
            synonyms=["user activity type", "نوع فعالیت کاربر"],
            columns=[
                ColumnSpec(
                    "TypeId",
                    semantic_type=SemanticType.IDENTIFIER,
                    primary_key=True,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "TypeName",
                    semantic_type=SemanticType.TEXT,
                    description="Activity type description.",
                    synonyms=["نوع فعالیت", "نوع اکشن", "activity type"],
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, sortable=True),
                ),
            ],
            profiles={
                "public": TableAccess(available=True),
                "analyst": TableAccess(available=True),
                "internal": TableAccess(available=True),
            },
        ),
        # 7. UPM.UserUnitPermissions
        TableSpec(
            ref=TableRef("UPM", "UserUnitPermissions"),
            description="Organizational unit permission assignments for system users.",
            columns=[
                ColumnSpec(
                    "UserId",
                    semantic_type=SemanticType.IDENTIFIER,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "UnitId",
                    semantic_type=SemanticType.IDENTIFIER,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
            ],
            profiles={
                "public": TableAccess(available=True),
                "analyst": TableAccess(available=True),
                "internal": TableAccess(available=True),
            },
        ),
        # 8. Cor.Persons
        TableSpec(
            ref=TableRef("Cor", "Persons"),
            description=(
                "Represents a real person/citizen and their identity information. "
                "This is NOT a system login account. Do NOT use this entity for questions about login users, usernames, roles, or user accounts."
            ),
            synonyms=[
                "person",
                "people",
                "citizen",
                "individual",
                "شخص",
                "فرد",
                "شهروند",
                "اشخاص",
                "افراد",
                "مؤدی",
            ],
            columns=[
                ColumnSpec(
                    "Id",
                    semantic_type=SemanticType.IDENTIFIER,
                    primary_key=True,
                    capabilities=ColumnCapabilities(
                        selectable=True,
                        filterable=True,
                        joinable=True,
                        sortable=True,
                        groupable=True,
                    ),
                ),
                ColumnSpec(
                    "FirstName",
                    semantic_type=SemanticType.TEXT,
                    description="First name of the person/citizen.",
                    synonyms=["نام", "اسم", "first name"],
                    capabilities=ColumnCapabilities(
                        selectable=True,
                        filterable=True,
                        sortable=True,
                        groupable=True,
                    ),
                ),
                ColumnSpec(
                    "LastName",
                    semantic_type=SemanticType.TEXT,
                    description="Last name of the person/citizen.",
                    synonyms=["نام خانوادگی", "فامیلی", "last name", "surname"],
                    capabilities=ColumnCapabilities(
                        selectable=True,
                        filterable=True,
                        sortable=True,
                        groupable=True,
                    ),
                ),
                ColumnSpec(
                    "FatherName",
                    semantic_type=SemanticType.TEXT,
                    description="Father's name.",
                    synonyms=["نام پدر", "father name"],
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "MotherName",
                    semantic_type=SemanticType.TEXT,
                    description="Mother's name.",
                    synonyms=["نام مادر", "mother name"],
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "NationalCode",
                    allowed=False,
                    access=ColumnAccessLevel.DENIED,
                    profiles={
                        "public": ColumnAccess.deny(),
                        "analyst": ColumnAccess.deny(),
                        "internal": ColumnAccess.deny(),
                    },
                    description="Encrypted by host layer; direct SQL access denied.",
                ),
                ColumnSpec(
                    "BirthCertificateNumber",
                    semantic_type=SemanticType.TEXT,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "BirthDate",
                    allowed=False,
                    access=ColumnAccessLevel.DENIED,
                    profiles={
                        "public": ColumnAccess.deny(),
                        "analyst": ColumnAccess.deny(),
                        "internal": ColumnAccess.deny(),
                    },
                    description="Encrypted by host layer; direct SQL access denied.",
                ),
                ColumnSpec(
                    "IssuePlace",
                    semantic_type=SemanticType.TEXT,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "PersonPicture",
                    semantic_type=SemanticType.TEXT,
                    capabilities=ColumnCapabilities(selectable=True),
                ),
                ColumnSpec(
                    "Address",
                    allowed=False,
                    access=ColumnAccessLevel.DENIED,
                    profiles={
                        "public": ColumnAccess.deny(),
                        "analyst": ColumnAccess.deny(),
                        "internal": ColumnAccess.deny(),
                    },
                    description="Encrypted by host layer; direct SQL access denied.",
                ),
                ColumnSpec(
                    "MobileNumber",
                    allowed=False,
                    access=ColumnAccessLevel.DENIED,
                    profiles={
                        "public": ColumnAccess.deny(),
                        "analyst": ColumnAccess.deny(),
                        "internal": ColumnAccess.deny(),
                    },
                    description="Encrypted by host layer; direct SQL access denied.",
                ),
                ColumnSpec(
                    "PhoneNumber",
                    allowed=False,
                    access=ColumnAccessLevel.DENIED,
                    profiles={
                        "public": ColumnAccess.deny(),
                        "analyst": ColumnAccess.deny(),
                        "internal": ColumnAccess.deny(),
                    },
                    description="Encrypted by host layer; direct SQL access denied.",
                ),
                ColumnSpec(
                    "PostalCode",
                    allowed=False,
                    access=ColumnAccessLevel.DENIED,
                    profiles={
                        "public": ColumnAccess.deny(),
                        "analyst": ColumnAccess.deny(),
                        "internal": ColumnAccess.deny(),
                    },
                    description="Encrypted by host layer; direct SQL access denied.",
                ),
                ColumnSpec(
                    "Job",
                    semantic_type=SemanticType.TEXT,
                    description="Occupation/Job.",
                    synonyms=["شغل", "حرفه", "کار", "job", "occupation"],
                    capabilities=ColumnCapabilities(
                        selectable=True,
                        filterable=True,
                        sortable=True,
                        groupable=True,
                    ),
                ),
                ColumnSpec(
                    "IsDeleted",
                    semantic_type=SemanticType.BOOLEAN,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "CreatedByUserId",
                    semantic_type=SemanticType.IDENTIFIER,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "ModifiedByUserId",
                    semantic_type=SemanticType.IDENTIFIER,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "CreationDateTime",
                    semantic_type=SemanticType.DATETIME,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, sortable=True),
                ),
                ColumnSpec(
                    "ModificationDateTime",
                    semantic_type=SemanticType.DATETIME,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, sortable=True),
                ),
                ColumnSpec(
                    "NationalityId",
                    semantic_type=SemanticType.IDENTIFIER,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "GenderId",
                    semantic_type=SemanticType.IDENTIFIER,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "ReligionId",
                    semantic_type=SemanticType.IDENTIFIER,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "HasBirthCertificate",
                    semantic_type=SemanticType.BOOLEAN,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
            ],
            required_filters=[
                RequiredFilter(column="IsDeleted", operator=FilterOperator.EQ, value=0)
            ],
            profiles={
                "public": TableAccess(available=True),
                "analyst": TableAccess(available=True),
                "internal": TableAccess(available=True),
            },
        ),
        # 9. Cor.Unit
        TableSpec(
            ref=TableRef("Cor", "Unit"),
            description="Organizational units / departments within the municipality.",
            synonyms=["unit", "department", "واحد", "بخش", "دپارتمان"],
            columns=[
                ColumnSpec(
                    "Id",
                    semantic_type=SemanticType.IDENTIFIER,
                    primary_key=True,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "UnitName",
                    semantic_type=SemanticType.TEXT,
                    description="Organizational unit name.",
                    synonyms=[
                        "واحد",
                        "نام واحد",
                        "بخش",
                        "unit",
                        "unit name",
                        "department",
                    ],
                    capabilities=ColumnCapabilities(
                        selectable=True,
                        filterable=True,
                        sortable=True,
                        groupable=True,
                    ),
                ),
                ColumnSpec(
                    "CityId",
                    semantic_type=SemanticType.IDENTIFIER,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "IsDeleted",
                    semantic_type=SemanticType.BOOLEAN,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "IsForCitizens",
                    semantic_type=SemanticType.BOOLEAN,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
            ],
            required_filters=[
                RequiredFilter(column="IsDeleted", operator=FilterOperator.EQ, value=0)
            ],
            profiles={
                "public": TableAccess(available=True),
                "analyst": TableAccess(available=True),
                "internal": TableAccess(available=True),
            },
        ),
        # 10. Cor.Cities
        TableSpec(
            ref=TableRef("Cor", "Cities"),
            description="Cities.",
            synonyms=["city", "cities", "شهر", "شهرها"],
            columns=[
                ColumnSpec(
                    "Id",
                    semantic_type=SemanticType.IDENTIFIER,
                    primary_key=True,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "CityName",
                    semantic_type=SemanticType.TEXT,
                    description="City name.",
                    synonyms=["شهر", "نام شهر", "city", "city name"],
                    capabilities=ColumnCapabilities(
                        selectable=True,
                        filterable=True,
                        sortable=True,
                        groupable=True,
                    ),
                ),
                ColumnSpec(
                    "ProvinceId",
                    semantic_type=SemanticType.IDENTIFIER,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "IsDeleted",
                    semantic_type=SemanticType.BOOLEAN,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
            ],
            required_filters=[
                RequiredFilter(column="IsDeleted", operator=FilterOperator.EQ, value=0)
            ],
            profiles={
                "public": TableAccess(available=True),
                "analyst": TableAccess(available=True),
                "internal": TableAccess(available=True),
            },
        ),
        # 11. Cor.Provinces
        TableSpec(
            ref=TableRef("Cor", "Provinces"),
            description="Provinces.",
            synonyms=["province", "provinces", "استان", "استان‌ها"],
            columns=[
                ColumnSpec(
                    "Id",
                    semantic_type=SemanticType.IDENTIFIER,
                    primary_key=True,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "ProvinceName",
                    semantic_type=SemanticType.TEXT,
                    description="Province name.",
                    synonyms=["استان", "نام استان", "province"],
                    capabilities=ColumnCapabilities(
                        selectable=True,
                        filterable=True,
                        sortable=True,
                        groupable=True,
                    ),
                ),
                ColumnSpec(
                    "IsDeleted",
                    semantic_type=SemanticType.BOOLEAN,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
            ],
            required_filters=[
                RequiredFilter(column="IsDeleted", operator=FilterOperator.EQ, value=0)
            ],
            profiles={
                "public": TableAccess(available=True),
                "analyst": TableAccess(available=True),
                "internal": TableAccess(available=True),
            },
        ),
        # 12. Cor.Nationalities
        TableSpec(
            ref=TableRef("Cor", "Nationalities"),
            description="Nationalities.",
            synonyms=["nationality", "nationalities", "ملیت", "تابعیت"],
            columns=[
                ColumnSpec(
                    "Id",
                    semantic_type=SemanticType.IDENTIFIER,
                    primary_key=True,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "Name",
                    semantic_type=SemanticType.TEXT,
                    description="Nationality name.",
                    synonyms=["ملیت", "تابعیت", "nationality"],
                    capabilities=ColumnCapabilities(
                        selectable=True,
                        filterable=True,
                        sortable=True,
                        groupable=True,
                    ),
                ),
                ColumnSpec(
                    "IsDeleted",
                    semantic_type=SemanticType.BOOLEAN,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
            ],
            required_filters=[
                RequiredFilter(column="IsDeleted", operator=FilterOperator.EQ, value=0)
            ],
            profiles={
                "public": TableAccess(available=True),
                "analyst": TableAccess(available=True),
                "internal": TableAccess(available=True),
            },
        ),
        # 13. Cor.Genders
        TableSpec(
            ref=TableRef("Cor", "Genders"),
            description="Gender classifications.",
            synonyms=["gender", "genders", "جنسیت"],
            columns=[
                ColumnSpec(
                    "Id",
                    semantic_type=SemanticType.IDENTIFIER,
                    primary_key=True,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "Desc",
                    semantic_type=SemanticType.TEXT,
                    description="Gender description.",
                    synonyms=["جنسیت", "gender"],
                    capabilities=ColumnCapabilities(
                        selectable=True,
                        filterable=True,
                        sortable=True,
                        groupable=True,
                    ),
                ),
                ColumnSpec(
                    "IsDeleted",
                    semantic_type=SemanticType.BOOLEAN,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
            ],
            required_filters=[
                RequiredFilter(column="IsDeleted", operator=FilterOperator.EQ, value=0)
            ],
            profiles={
                "public": TableAccess(available=True),
                "analyst": TableAccess(available=True),
                "internal": TableAccess(available=True),
            },
        ),
        # 14. Cor.Religions
        TableSpec(
            ref=TableRef("Cor", "Religions"),
            description="Religions.",
            synonyms=["religion", "religions", "دین", "مذهب"],
            columns=[
                ColumnSpec(
                    "Id",
                    semantic_type=SemanticType.IDENTIFIER,
                    primary_key=True,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "Desc",
                    semantic_type=SemanticType.TEXT,
                    description="Religion description.",
                    synonyms=["دین", "مذهب", "religion"],
                    capabilities=ColumnCapabilities(
                        selectable=True,
                        filterable=True,
                        sortable=True,
                        groupable=True,
                    ),
                ),
                ColumnSpec(
                    "IsDeleted",
                    semantic_type=SemanticType.BOOLEAN,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
            ],
            required_filters=[
                RequiredFilter(column="IsDeleted", operator=FilterOperator.EQ, value=0)
            ],
            profiles={
                "public": TableAccess(available=True),
                "analyst": TableAccess(available=True),
                "internal": TableAccess(available=True),
            },
        ),
        # 15. Cor.Organizations
        TableSpec(
            ref=TableRef("Cor", "Organizations"),
            description="Organizations and corporate legal entities.",
            synonyms=["organization", "company", "سازمان", "شرکت", "مؤسسه"],
            columns=[
                ColumnSpec(
                    "Id",
                    semantic_type=SemanticType.IDENTIFIER,
                    primary_key=True,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True, joinable=True),
                ),
                ColumnSpec(
                    "Name",
                    semantic_type=SemanticType.TEXT,
                    description="Organization name.",
                    synonyms=["سازمان", "شرکت", "مؤسسه", "organization", "company"],
                    capabilities=ColumnCapabilities(
                        selectable=True,
                        filterable=True,
                        sortable=True,
                        groupable=True,
                    ),
                ),
                ColumnSpec(
                    "EconomicCode",
                    semantic_type=SemanticType.IDENTIFIER,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "Address",
                    semantic_type=SemanticType.TEXT,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "PhoneNumber",
                    semantic_type=SemanticType.PHONE,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "MobileNumber",
                    semantic_type=SemanticType.PHONE,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
                ColumnSpec(
                    "IsDeleted",
                    semantic_type=SemanticType.BOOLEAN,
                    capabilities=ColumnCapabilities(selectable=True, filterable=True),
                ),
            ],
            required_filters=[
                RequiredFilter(column="IsDeleted", operator=FilterOperator.EQ, value=0)
            ],
            profiles={
                "public": TableAccess(available=True),
                "analyst": TableAccess(available=True),
                "internal": TableAccess(available=True),
            },
        ),
    ]

    relationships = [
        RelationshipSpec(
            source_table=TableRef("UPM", "Users"),
            source_column="Id",
            target_table=TableRef("UPM", "UserRoles"),
            target_column="UserId",
        ),
        RelationshipSpec(
            source_table=TableRef("UPM", "Roles"),
            source_column="Id",
            target_table=TableRef("UPM", "UserRoles"),
            target_column="RoleId",
        ),
        RelationshipSpec(
            source_table=TableRef("UPM", "Users"),
            source_column="Id",
            target_table=TableRef("UPM", "UserClaims"),
            target_column="UserId",
        ),
        RelationshipSpec(
            source_table=TableRef("UPM", "Users"),
            source_column="Id",
            target_table=TableRef("UPM", "UserLog"),
            target_column="UserId",
        ),
        RelationshipSpec(
            source_table=TableRef("UPM", "UserActivityType"),
            source_column="TypeId",
            target_table=TableRef("UPM", "UserLog"),
            target_column="UserActivityTypeId",
        ),
        RelationshipSpec(
            source_table=TableRef("UPM", "Users"),
            source_column="Id",
            target_table=TableRef("UPM", "UserUnitPermissions"),
            target_column="UserId",
        ),
        RelationshipSpec(
            source_table=TableRef("Cor", "Unit"),
            source_column="Id",
            target_table=TableRef("UPM", "UserUnitPermissions"),
            target_column="UnitId",
        ),
        RelationshipSpec(
            source_table=TableRef("Cor", "Unit"),
            source_column="Id",
            target_table=TableRef("UPM", "Users"),
            target_column="UnitId",
        ),
        RelationshipSpec(
            source_table=TableRef("Cor", "Cities"),
            source_column="Id",
            target_table=TableRef("Cor", "Unit"),
            target_column="CityId",
        ),
        RelationshipSpec(
            source_table=TableRef("Cor", "Provinces"),
            source_column="Id",
            target_table=TableRef("Cor", "Cities"),
            target_column="ProvinceId",
        ),
        RelationshipSpec(
            source_table=TableRef("Cor", "Nationalities"),
            source_column="Id",
            target_table=TableRef("Cor", "Persons"),
            target_column="NationalityId",
        ),
        RelationshipSpec(
            source_table=TableRef("Cor", "Genders"),
            source_column="Id",
            target_table=TableRef("Cor", "Persons"),
            target_column="GenderId",
        ),
        RelationshipSpec(
            source_table=TableRef("Cor", "Religions"),
            source_column="Id",
            target_table=TableRef("Cor", "Persons"),
            target_column="ReligionId",
        ),
    ]

    execution_policy = ExecutionPolicy(
        allow_select_star=False,
        max_joins=5,
        max_rows=50,
        timeout_seconds=30,
        allow_subqueries=True,
        allow_ctes=True,
        allow_cross_join=False,
    )

    return QuerySpace(
        tables=tables,
        relationships=relationships,
        execution_policy=execution_policy,
    )


# =============================================================================
# 2. DATABASE & LLM SETUP HELPERS
# =============================================================================
def build_engine() -> tuple[Engine | None, str]:
    """Connect using a SQLAlchemy URL or QuerySmith's component DB settings."""
    db_url = os.getenv(DATABASE_URL_ENV)

    try:
        if db_url and db_url.strip():
            engine = create_engine(db_url)
            destination = db_url.split("@")[-1] if "@" in db_url else "database"
        else:
            config = load_config()
            engine = make_engine(config)
            destination = f"{config.server}/{config.database}"
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine, f"Connected ({destination})"
    except Exception as exc:  # noqa: BLE001
        return None, f"Connection failed ({exc})"


def build_llm_client() -> tuple[OpenAICompatibleClient | None, str]:
    """Initialize LLM Client using environment API keys."""
    try:
        client = OpenAICompatibleClient()
        return client, f"Initialized ({client.model_name})"
    except Exception as exc:  # noqa: BLE001
        return None, f"LLM configuration missing ({exc})"


# =============================================================================
# 3. RESULT FORMATTING & INTERACTIVE DISPLAY
# =============================================================================
def format_terminal_table(
    rows: Sequence[dict[str, Any]], max_rows: int = 20
) -> str:
    """Format query result rows into a clean terminal ASCII table."""
    if not rows:
        return "No rows returned."

    headers = list(rows[0].keys())
    table_data = []
    for row in rows[:max_rows]:
        row_str = [
            str(row.get(h, "")) if row.get(h) is not None else "NULL"
            for h in headers
        ]
        table_data.append(row_str)

    widths = [len(h) for h in headers]
    for row_str in table_data:
        for i, val in enumerate(row_str):
            widths[i] = max(widths[i], len(val))

    widths = [min(max(w, 4), 35) for w in widths]

    def format_row(row_vals: list[str]) -> str:
        formatted = []
        for val, w in zip(row_vals, widths):
            if len(val) > w:
                val = val[: w - 3] + "..."
            formatted.append(val.ljust(w))
        return " | ".join(formatted)

    header_line = format_row(headers)
    separator = "-+-".join("-" * w for w in widths)
    data_lines = [format_row(r) for r in table_data]

    lines = [f"{len(rows)} row(s)\n", header_line, separator] + data_lines
    if len(rows) > max_rows:
        lines.append(
            f"\nShowing {max_rows} of {len(rows)} rows. Truncated by display limit."
        )
    return "\n".join(lines)


def print_banner(state: DemoState, conn_msg: str, llm_msg: str) -> None:
    """Print the interactive playground header banner."""
    print("\n" + "=" * 70)
    print(" QUERYSMITH v0.2.0 — INTERACTIVE DATABASE PLAYGROUND")
    print("=" * 70)
    print(f" Database:   {conn_msg}")
    print(f" LLM Client: {llm_msg}")
    print(" QuerySpace: municipal_playground (15 UPM + Cor tables)")
    print(f" Profile:    {state.access_profile}")
    print(f" Execution:  {'ENABLED' if state.execute_queries else 'DISABLED'}")
    print("=" * 70)
    print(" Type your question in Persian or English.\n")
    print(" Commands:")
    print("   /profile public  - Switch access profile to 'public'")
    print("   /profile analyst - Switch access profile to 'analyst'")
    print("   /profile internal- Switch access profile to 'internal'")
    print("   /execute on      - Enable query execution on database")
    print("   /execute off     - Disable query execution (preview mode)")
    print("   /sql <query>     - Test PolicyEngine with manual raw SQL")
    print("   /report          - Show detailed authorization report of last query")
    print("   /help            - Display this help banner")
    print("   /quit            - Exit playground\n")


def handle_command(cmd_text: str, state: DemoState) -> bool:
    """Handle interactive REPL slash commands."""
    cmd = cmd_text.strip().lower()
    if cmd in ("/quit", "/exit"):
        print("\nExiting QuerySmith playground. Goodbye!")
        return False

    if cmd == "/help":
        print("\nPlayground Help:")
        print("  Ask any natural language question in Persian or English.")
        print("  Example: 'کاربری با اسم سینا بهم بده'")
        print("  Example: 'شخصی با اسم سینا پیدا کن'")
        print("  Example: 'نقشهای کاربر سینا چیست؟'")
        print("  Example: 'آخرین فعالیتهای کاربر سینا را نشان بده'")
        return True

    if cmd.startswith("/profile"):
        parts = cmd.split(maxsplit=1)
        if len(parts) < 2 or parts[1] not in ("public", "analyst", "internal"):
            print("Usage: /profile public | analyst | internal")
        else:
            state.access_profile = parts[1]
            print(f"✓ Access profile updated to: '{state.access_profile}'")
        return True

    if cmd.startswith("/execute"):
        parts = cmd.split(maxsplit=1)
        if len(parts) < 2 or parts[1] not in ("on", "off"):
            print("Usage: /execute on | off")
        else:
            state.execute_queries = parts[1] == "on"
            status_str = "ENABLED" if state.execute_queries else "DISABLED"
            print(f"✓ Database execution is now {status_str}")
        return True

    if cmd == "/report":
        if state.last_prepared is None and state.last_error is None:
            print("No query has been authorized yet.")
            return True
        if state.last_prepared:
            report = state.last_prepared.authorization
            print("\n" + "=" * 70)
            print(" LAST AUTHORIZATION REPORT")
            print("=" * 70)
            print(f" Allowed:          {report.allowed if report else 'N/A'}")
            print(f" Authorized SQL:   {state.last_prepared.sql}")
            print(f" Tables Used:      {', '.join(report.tables_used) if report else 'N/A'}")
            print(f" Applied Policies: {', '.join(state.last_prepared.applied_policies)}")
            if report and report.applied_masks:
                print(f" Applied Masks:    {', '.join(report.applied_masks)}")
        elif state.last_error:
            print("\n" + "=" * 70)
            print(" LAST DENIAL REPORT")
            print("=" * 70)
            print(f" Error:  {state.last_error}")
        return True

    if cmd.startswith("/sql"):
        raw_sql = cmd_text[4:].strip()
        if not raw_sql:
            print("Usage: /sql <raw_sql_query>")
            return True
        run_raw_sql(raw_sql, state)
        return True

    print(f"Unknown command '{cmd_text}'. Type /help for available commands.")
    return True


def run_raw_sql(raw_sql: str, state: DemoState) -> None:
    """Authorize and optionally execute a manual raw SQL string."""
    if state.resolved_space is None:
        print("❌ QuerySpace not resolved.")
        return

    print("\n" + "-" * 70)
    print(f" MANUAL RAW SQL INPUT: {raw_sql}")
    print(f" ACTIVE PROFILE: {state.access_profile}")
    print("-" * 70)

    policy_engine = PolicyEngine()

    from querysmith.profiles import AccessProfileResolver

    profiled_space = AccessProfileResolver().resolve(
        state.resolved_space, state.access_profile
    )

    try:
        authorized = policy_engine.authorize_and_apply(
            raw_sql, profiled_space, {}
        )
        state.last_prepared = authorized
        state.last_error = None

        print("\n[AUTHORIZED SAFE SQL]")
        print(authorized.sql)

        report = authorized.authorization
        if report:
            print("\n[AUTHORIZATION REPORT]")
            print(f"  Allowed:           {report.allowed}")
            print(f"  Tables Referenced: {', '.join(report.tables_used)}")

        if state.execute_queries:
            if state.engine is None:
                print("\n⚠ Execution skipped: Database engine is not connected.")
            else:
                print("\n[EXECUTING ON DATABASE]")
                res = execute_authorized_query(
                    state.engine,
                    authorized,
                    profiled_space,
                )
                print(format_terminal_table(res.rows))
    except Exception as exc:  # noqa: BLE001 - REPL boundary reports user-facing errors
        state.last_error = exc
        print("\n" + "!" * 70)
        print(" [SECURITY AUTHORIZATION DENIED / REJECTED]")
        print("!" * 70)
        code = getattr(exc, "code", type(exc).__name__)
        code_str = code.value if hasattr(code, "value") else str(code)
        print(f"  Code:   {code_str}")
        print(f"  Reason: {exc}")


def run_question(question: str, state: DemoState) -> None:
    """Process a natural language question through QuerySmith pipeline."""
    if state.resolved_space is None:
        print("❌ Cannot process question: QuerySpace catalog not resolved.")
        return

    if state.llm_client is None:
        print("❌ LLM configuration missing. Set OPENAI_API_KEY, AVALAI_API_KEY, or QUERYSMITH_LLM_API_KEY.")
        print("   Use /sql <raw_sql> to test PolicyEngine manually.")
        return

    print("\n" + "-" * 70)
    print(f" QUESTION: {question}")
    print(f" ACTIVE PROFILE: {state.access_profile}")
    print("-" * 70)

    audit_logger = PythonLoggingAuditLogger(
        policy=AuditLoggingPolicy(log_question=True)
    )

    try:
        authorized: AuthorizedQuery = authorize_query_in_space(
            question,
            state.resolved_space,
            state.llm_client,
            access_profile=state.access_profile,
            audit_logger=audit_logger,
        )
        state.last_prepared = authorized
        state.last_error = None

        print("\n[AUTHORIZED SAFE SQL]")
        print(authorized.sql)

        report = authorized.authorization
        if report:
            print("\n[AUTHORIZATION REPORT]")
            print(f"  Allowed:           {report.allowed}")
            print(f"  Tables Referenced: {', '.join(report.tables_used)}")
            if report.columns_used:
                sel_cols = report.columns_used.get("select", ())
                print(
                    f"  SELECT Columns:    {', '.join(sel_cols) if sel_cols else 'N/A'}"
                )
            if authorized.applied_policies:
                print(f"  Applied Policies:  {', '.join(authorized.applied_policies)}")
            if report.applied_masks:
                print(f"  Applied Masks:     {', '.join(report.applied_masks)}")

        if state.execute_queries:
            if state.engine is None:
                print("\n⚠ Execution skipped: Database engine is not connected.")
            else:
                print("\n[EXECUTING ON DATABASE]")
                res = execute_authorized_query(
                    state.engine,
                    authorized,
                    state.resolved_space,
                    access_profile=state.access_profile,
                    audit_logger=audit_logger,
                )
                print(format_terminal_table(res.rows))
                if res.truncated:
                    print("ℹ Result rows truncated by QuerySmith max_rows policy.")

    except Exception as exc:  # noqa: BLE001 - REPL boundary reports user-facing errors
        state.last_error = exc
        print("\n" + "!" * 70)
        print(" [SECURITY AUTHORIZATION DENIED / REJECTED]")
        print("!" * 70)
        code = getattr(exc, "code", type(exc).__name__)
        code_str = code.value if hasattr(code, "value") else str(code)
        print(f"  Code:   {code_str}")
        print(f"  Reason: {exc}")


def interactive_loop(state: DemoState) -> None:
    """Run the interactive natural language prompt loop."""
    while True:
        try:
            prompt_str = f"querysmith ({state.access_profile})> "
            user_input = input(prompt_str).strip()
            if not user_input:
                continue

            if user_input.startswith("/"):
                keep_running = handle_command(user_input, state)
                if not keep_running:
                    break
            else:
                run_question(user_input, state)

        except (KeyboardInterrupt, EOFError):
            print("\nExiting playground.")
            break


# =============================================================================
# MAIN ENTRYPOINT
# =============================================================================
def main() -> None:
    """Initialize engine, resolve QuerySpace against physical database, and launch interactive playground."""
    load_dotenv()
    state = DemoState()

    # 1. Connect to physical database
    engine, conn_msg = build_engine()
    state.engine = engine

    if engine is None:
        print("=" * 70)
        print(" WARNING: SQL Server database is not available.")
        print(f" {conn_msg}")
        print(" Set QUERYSMITH_DATABASE_URL or the DB_* variables in .env.")
        print("=" * 70)

    # 2. Initialize LLM Client
    llm_client, llm_msg = build_llm_client()
    state.llm_client = llm_client

    # 3. Declare developer QuerySpace
    query_space = build_query_space()

    # 4. Resolve QuerySpace against physical catalog
    if engine is not None:
        try:
            resolver = CatalogResolver(SQLServerIntrospector(engine))
            state.resolved_space = resolver.resolve(query_space)
        except Exception as exc:  # noqa: BLE001
            print(f"\n❌ QuerySpace catalog resolution failed against live database: {exc}")
            print("Ensure physical database contains [UPM] and [Cor] tables.")
            sys.exit(1)
    else:
        # Introspect using mock catalog when offline
        from querysmith.catalog import CatalogColumn, CatalogSnapshot, CatalogTable

        class MockIntrospector:
            def inspect_tables(self, refs: Any) -> CatalogSnapshot:
                tables = []
                for t in query_space.tables:
                    cols = []
                    for c in t.columns:
                        if c.primary_key or c.name.endswith("Id"):
                            data_type = "int"
                        elif c.semantic_type is SemanticType.BOOLEAN:
                            data_type = "bit"
                        elif c.semantic_type is SemanticType.DATE:
                            data_type = "date"
                        elif c.semantic_type is SemanticType.DATETIME:
                            data_type = "datetime2"
                        elif c.semantic_type in {
                            SemanticType.CURRENCY,
                            SemanticType.QUANTITY,
                            SemanticType.PERCENTAGE,
                            SemanticType.DURATION,
                        }:
                            data_type = "decimal"
                        else:
                            data_type = "nvarchar"
                        cols.append(
                            CatalogColumn(
                                name=c.name,
                                data_type=data_type,
                                nullable=True,
                                primary_key=c.primary_key,
                            )
                        )
                    tables.append(CatalogTable(ref=t.ref, columns=tuple(cols)))
                return CatalogSnapshot(requested_refs=tuple(refs), tables=tuple(tables))

        resolver = CatalogResolver(MockIntrospector())
        state.resolved_space = resolver.resolve(query_space)

    # 5. Launch Interactive Banner & REPL Loop
    print_banner(state, conn_msg, llm_msg)
    interactive_loop(state)


if __name__ == "__main__":
    main()
