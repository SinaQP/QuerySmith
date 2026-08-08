"""Tests for language model SQL generation."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from querysmith.guard import UnsafeQueryError
from querysmith.llm import (
    OpenAICompatibleClient,
    build_sql_prompt,
    generate_sql,
)

SCHEMA_TEXT = "Database schema:\ndbo.Users\n- Id int [PK]\n- Name nvarchar\n\nRelationships: <none>"


class FakeClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def test_build_sql_prompt_includes_user_question() -> None:
    prompt = build_sql_prompt("کاربران را نمایش بده", SCHEMA_TEXT)

    assert "کاربران را نمایش بده" in prompt


def test_build_sql_prompt_includes_schema_text() -> None:
    prompt = build_sql_prompt("show users", SCHEMA_TEXT)

    assert SCHEMA_TEXT in prompt


def test_build_sql_prompt_mentions_sql_server_or_tsql() -> None:
    prompt = build_sql_prompt("show users", SCHEMA_TEXT)

    assert "SQL Server" in prompt or "T-SQL" in prompt


def test_build_sql_prompt_says_output_sql_only() -> None:
    prompt = build_sql_prompt("show users", SCHEMA_TEXT)

    assert "Return SQL only" in prompt


def test_build_sql_prompt_explains_semantics_capabilities_and_wildcards() -> None:
    prompt = build_sql_prompt("count users", SCHEMA_TEXT)

    assert "Semantic aliases are descriptive only" in prompt
    assert "allowed operations" in prompt
    assert "advisory business rules" in prompt
    assert "COUNT(*) is allowed" in prompt


def test_generate_sql_returns_safe_select_from_fake_client() -> None:
    client = FakeClient("SELECT Id, Name FROM dbo.Users")

    assert generate_sql("show users", SCHEMA_TEXT, client) == (
        "SELECT Id, Name FROM dbo.Users"
    )


def test_generate_sql_removes_markdown_sql_fences() -> None:
    client = FakeClient(
        """
        ```sql
        SELECT Id FROM dbo.Users
        ```
        """
    )

    assert generate_sql("show user ids", SCHEMA_TEXT, client) == (
        "SELECT Id FROM dbo.Users"
    )


def test_generate_sql_raises_for_delete() -> None:
    client = FakeClient("DELETE FROM dbo.Users")

    with pytest.raises(UnsafeQueryError):
        generate_sql("delete users", SCHEMA_TEXT, client)


def test_generate_sql_raises_for_multiple_statements() -> None:
    client = FakeClient("SELECT Id FROM dbo.Users; DROP TABLE dbo.Users")

    with pytest.raises(UnsafeQueryError):
        generate_sql("show users", SCHEMA_TEXT, client)


def test_generate_sql_sends_prompt_to_client() -> None:
    client = FakeClient("SELECT Id FROM dbo.Users")

    generate_sql("show users", SCHEMA_TEXT, client)

    assert len(client.prompts) == 1
    assert "show users" in client.prompts[0]
    assert SCHEMA_TEXT in client.prompts[0]


def test_openai_compatible_client_accepts_explicit_config() -> None:
    client = OpenAICompatibleClient(
        api_key="test-key",
        base_url="https://example.test/v1",
        model_name="test-model",
    )

    assert client.api_key == "test-key"
    assert client.base_url == "https://example.test/v1"
    assert client.model_name == "test-model"


def test_openai_compatible_client_default_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QUERYSMITH_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("AVALAI_BASE_URL", raising=False)

    client = OpenAICompatibleClient(api_key="test-key")

    assert client.base_url == "https://api.avalai.ir/v1"


def test_openai_compatible_client_env_vars_override_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUERYSMITH_LLM_API_KEY", "env-key")
    monkeypatch.setenv("QUERYSMITH_LLM_BASE_URL", "https://env.test/v1")
    monkeypatch.setenv("QUERYSMITH_LLM_MODEL", "env-model")

    client = OpenAICompatibleClient()

    assert client.api_key == "env-key"
    assert client.base_url == "https://env.test/v1"
    assert client.model_name == "env-model"


def test_openai_compatible_client_explicit_args_override_env_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUERYSMITH_LLM_API_KEY", "env-key")
    monkeypatch.setenv("QUERYSMITH_LLM_BASE_URL", "https://env.test/v1")
    monkeypatch.setenv("QUERYSMITH_LLM_MODEL", "env-model")

    client = OpenAICompatibleClient(
        api_key="explicit-key",
        base_url="https://explicit.test/v1",
        model_name="explicit-model",
    )

    assert client.api_key == "explicit-key"
    assert client.base_url == "https://explicit.test/v1"
    assert client.model_name == "explicit-model"


def test_openai_compatible_client_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QUERYSMITH_LLM_API_KEY", raising=False)
    monkeypatch.delenv("AVALAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="QUERYSMITH_LLM_API_KEY"):
        OpenAICompatibleClient()


def test_openai_compatible_client_complete_uses_internal_client() -> None:
    client = OpenAICompatibleClient(
        api_key="test-key",
        base_url="https://example.test/v1",
        model_name="test-model",
    )
    fake_chat_client = FakeOpenAIChatClient(content="SELECT Id FROM dbo.Users")
    client.client = fake_chat_client

    assert client.complete("prompt") == "SELECT Id FROM dbo.Users"
    assert fake_chat_client.chat.completions.prompt == "prompt"
    assert fake_chat_client.chat.completions.model == "test-model"


def test_openai_compatible_client_complete_rejects_empty_response() -> None:
    client = OpenAICompatibleClient(
        api_key="test-key",
        base_url="https://example.test/v1",
        model_name="test-model",
    )
    client.client = FakeOpenAIChatClient(content="  ")

    with pytest.raises(RuntimeError):
        client.complete("prompt")


@dataclass
class FakeMessage:
    content: str | None


@dataclass
class FakeChoice:
    message: FakeMessage


@dataclass
class FakeCompletion:
    choices: list[FakeChoice]


class FakeCompletions:
    def __init__(self, content: str | None) -> None:
        self.content = content
        self.prompt = ""
        self.model = ""

    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: int,
    ) -> FakeCompletion:
        self.model = model
        self.prompt = messages[1]["content"]
        assert temperature == 0
        return FakeCompletion(choices=[FakeChoice(FakeMessage(self.content))])


class FakeChat:
    def __init__(self, content: str | None) -> None:
        self.completions = FakeCompletions(content)


class FakeOpenAIChatClient:
    def __init__(self, content: str | None) -> None:
        self.chat = FakeChat(content)
