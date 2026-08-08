"""Tests for QuerySmith Django ORM Adapter."""

from __future__ import annotations

import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        SECRET_KEY="test-secret-key",
        INSTALLED_APPS=["django.contrib.contenttypes", "django.contrib.auth"],
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    )
django.setup()

from django.db import models

from querysmith.django_adapter import (
    DjangoCatalogIntrospector,
    django_models_to_query_space,
    parse_db_table,
)
from querysmith.models import TableRef
from querysmith.resolver import CatalogResolver


class SampleProvince(models.Model):
    province_name = models.CharField(max_length=30, db_column="ProvinceName")
    is_deleted = models.BooleanField(default=False, db_column="IsDeleted")

    class Meta:
        app_label = "core"
        db_table = "Cor].[Provinces"


class SampleCity(models.Model):
    city_name = models.CharField(max_length=30, db_column="CityName")
    is_deleted = models.BooleanField(default=False, db_column="IsDeleted")
    province_id = models.ForeignKey(
        SampleProvince, on_delete=models.CASCADE, db_column="ProvinceId"
    )

    class Meta:
        app_label = "core"
        db_table = "Cor].[Cities"


class SamplePerson(models.Model):
    first_name = models.CharField(max_length=60, db_column="FirstName")
    last_name = models.CharField(max_length=60, db_column="LastName")
    national_code = models.CharField(max_length=100, db_column="NationalCode")

    class Meta:
        app_label = "core"
        db_table = "Cor].[Persons"


def test_parse_db_table():
    assert parse_db_table("Cor].[Provinces") == TableRef("Cor", "Provinces")
    assert parse_db_table("[Cor].[Cities]") == TableRef("Cor", "Cities")
    assert parse_db_table("Cor].[Villages ") == TableRef("Cor", "Villages")
    assert parse_db_table("Form") == TableRef("Cor", "Form")


def test_django_models_to_query_space():
    space = django_models_to_query_space([SampleProvince, SampleCity, SamplePerson])
    space.validate()

    assert len(space.tables) == 3

    prov_table = space.get_table(TableRef("Cor", "Provinces"))
    assert prov_table is not None
    assert prov_table.get_column("ProvinceName") is not None

    city_table = space.get_table(TableRef("Cor", "Cities"))
    assert city_table is not None
    assert city_table.get_column("ProvinceId") is not None

    assert len(space.relationships) == 1
    rel = space.relationships[0]
    assert rel.source_table == TableRef("Cor", "Provinces")
    assert rel.target_table == TableRef("Cor", "Cities")


def test_django_catalog_introspector():
    models_list = [SampleProvince, SampleCity, SamplePerson]
    space = django_models_to_query_space(models_list)
    introspector = DjangoCatalogIntrospector(models_list)

    resolver = CatalogResolver(introspector)
    resolved = resolver.resolve(space)

    assert len(resolved.tables) == 3
    prov_resolved = resolved.get_table(TableRef("Cor", "Provinces"))
    assert prov_resolved.get_column("ProvinceName") is not None
