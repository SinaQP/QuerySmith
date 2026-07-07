"""Language model interface for safe SQL generation."""

from __future__ import annotations

import os
import re
from typing import Protocol

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from openai import OpenAI

from querysmith.guard import validate_safe_select


_DEFAULT_BASE_URL = "https://api.avalai.ir/v1"
_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
_SYSTEM_MESSAGE = (
    "You generate conservative SQL Server T-SQL SELECT queries only. "
    "Return SQL only."
)


class LLMClient(Protocol):
    """Minimal client protocol used by SQL generation."""

    def complete(self, prompt: str) -> str:
        """Return a model completion for the provided prompt."""


class OpenAICompatibleClient:
    """OpenAI-compatible client with AvalAI defaults."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self.api_key = api_key or _first_env_value(
            "QUERYSMITH_LLM_API_KEY",
            "AVALAI_API_KEY",
            "OPENAI_API_KEY",
        )
        self.base_url = base_url or _first_env_value(
            "QUERYSMITH_LLM_BASE_URL",
            "AVALAI_BASE_URL",
        ) or _DEFAULT_BASE_URL
        self.model_name = (
            model_name
            or os.getenv("QUERYSMITH_LLM_MODEL")
            or _DEFAULT_MODEL
        )
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def complete(self, prompt: str) -> str:
        """Return a chat completion for the prompt."""

        completion = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": _SYSTEM_MESSAGE},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        content = completion.choices[0].message.content
        if content is None or not content.strip():
            raise RuntimeError("LLM returned an empty SQL response.")

        return content

    def get_model(self) -> ChatOpenAI:
        """Return a LangChain chat model configured like this client."""

        return ChatOpenAI(
            model=self.model_name,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=0,
        )

    def get_embeddings(self) -> OpenAIEmbeddings:
        """Return LangChain OpenAI-compatible embeddings."""

        return OpenAIEmbeddings(
            model=_DEFAULT_EMBEDDING_MODEL,
            api_key=self.api_key,
            base_url=self.base_url,
        )


def build_sql_prompt(question: str, schema_text: str) -> str:
    """Build the SQL Server query-generation prompt."""

    return "\n".join(
        [
            "Instructions:",
            "- Generate SQL Server T-SQL only.",
            "- Return exactly one query.",
            "- Return SQL only; do not include markdown fences.",
            "- Do not explain the query.",
            "- Use only SELECT or WITH ... SELECT.",
            "- Do not use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, MERGE, "
            "TRUNCATE, EXEC, stored procedures, temp tables, SELECT INTO, "
            "OUTPUT INTO, or multiple statements.",
            "- Use only tables and columns present in the provided schema.",
            "- Prefer explicit JOINs using the Relationships section.",
            "- Use SQL Server syntax.",
            "- For Persian and English user questions, infer the intended query "
            "from the provided schema.",
            "- If the question is ambiguous, produce the safest useful SELECT "
            "query using only available schema.",
            "- Never invent table names or column names.",
            "- If the schema is insufficient, return a conservative SELECT query "
            "over the most relevant available table instead of inventing columns.",
            "",
            "Schema:",
            schema_text.strip(),
            "",
            "User question:",
            question.strip(),
        ]
    )


def generate_sql(
    question: str,
    schema_text: str,
    client: LLMClient,
) -> str:
    """Generate and validate a safe SQL Server SELECT query."""

    prompt = build_sql_prompt(question=question, schema_text=schema_text)
    response = client.complete(prompt)
    sql = _clean_sql_response(response)
    return validate_safe_select(sql)


def _clean_sql_response(response: str) -> str:
    """Strip whitespace and remove one surrounding markdown SQL fence."""

    cleaned = response.strip()
    fenced_match = re.fullmatch(
        r"```(?:sql|tsql)?\s*\n?(.*?)\n?```",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if fenced_match is not None:
        return fenced_match.group(1).strip()

    return cleaned


def _first_env_value(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value

    return ""
