# QuerySmith

QuerySmith is a Python 3.11+ package that turns Persian and English natural-language questions into Microsoft SQL Server T-SQL `SELECT` queries. It reads schema metadata, prompts an LLM with that context, validates the generated SQL, and can execute approved queries through SQL Server.

> **Early release:** QuerySmith is being prepared for its first public PyPI release.

## Features

- SQL Server schema introspection for tables, columns, primary keys, and foreign keys.
- Persian and English question support in the SQL-generation prompt.
- T-SQL query generation through an OpenAI-compatible client, with AvalAI defaults.
- Environment-based AvalAI and OpenAI-compatible configuration.
- A conservative guard that allows one `SELECT` or `WITH ... SELECT` query and rejects comments, multiple statements, DDL/DML, procedure access, `SELECT INTO`, external data access, and linked-server-style object names.
- Python helpers for configuration, connection creation, query generation, validation, and guarded execution.

## Installation

### PyPI

After the first PyPI release, install QuerySmith with:

```bash
python -m pip install querysmith
```

### From source

```bash
git clone https://github.com/SinaQP/QuerySmith.git
cd QuerySmith
python -m venv .venv
```

Activate the environment:

```bash
# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install QuerySmith (and, for contributors, its configured development dependencies):

```bash
python -m pip install -e .
python -m pip install -e ".[dev]"
```

## Supported Python versions

QuerySmith requires Python 3.11 or newer.

## SQL Server prerequisites

QuerySmith requires access to a Microsoft SQL Server instance and credentials for the target database. Configure a server or host, optional port, database, username, password, and the installed ODBC driver name. Windows authentication is supported by setting `DB_TRUSTED_CONNECTION=true`.

> **ODBC driver required:** Installing `pyodbc` does not necessarily install the Microsoft SQL Server ODBC driver. `pyodbc` is the Python adapter; Microsoft ODBC Driver 18 for SQL Server is a separate system-level driver that may also be required. Driver installation differs across Windows, Linux, and macOS. Follow Microsoft's official ODBC-driver installation documentation for your platform, and make sure `DB_DRIVER` exactly matches an installed driver.

To view available driver names:

```python
import pyodbc

print(pyodbc.drivers())
```

`ODBC Driver 18 for SQL Server` is a common choice. QuerySmith's code defaults to version 17 when `DB_DRIVER` is not set, so set this variable explicitly when using version 18.

## Environment configuration

Create a local configuration file and keep it out of version control:

```bash
cp .env.example .env
```

```powershell
Copy-Item .env.example .env
```

`.env` can contain database passwords and API keys; never commit it.

### SQL Server settings

| Variable | Required | Purpose |
| --- | --- | --- |
| `DB_SERVER` or `DB_HOST` | Yes | SQL Server host or server name. |
| `DB_PORT` | No | Port appended to a host as `host,port`; omit for a named instance. |
| `DB_DATABASE` or `DB_NAME` | Yes | Target database name. |
| `DB_USERNAME` or `DB_USER` | Yes* | SQL Server login name. |
| `DB_PASSWORD` | Yes* | SQL Server login password. |
| `DB_DRIVER` | No | Installed driver name, such as `ODBC Driver 18 for SQL Server`. |
| `DB_TRUSTED_CONNECTION` | No | Set to `true`, `1`, or `yes` to use Windows trusted authentication. |

\*These values are currently required by `load_config()` even when trusted authentication is enabled.

### LLM settings

`OpenAICompatibleClient` selects the first non-empty API key from `QUERYSMITH_LLM_API_KEY`, `AVALAI_API_KEY`, and `OPENAI_API_KEY`. Its base URL comes from `QUERYSMITH_LLM_BASE_URL` or `AVALAI_BASE_URL`, otherwise it defaults to `https://api.avalai.ir/v1`. `QUERYSMITH_LLM_MODEL` selects the model and defaults to `gpt-4o-mini`.

There is no `LLM_PROVIDER` setting: select a provider by supplying its API key and, where needed, its compatible base URL.

### AvalAI

AvalAI is used through its OpenAI-compatible API by default. A minimal configuration is:

```dotenv
AVALAI_API_KEY=your-avalai-api-key
AVALAI_BASE_URL=https://api.avalai.ir/v1
QUERYSMITH_LLM_MODEL=gpt-4o-mini
```

You can instead use the provider-neutral `QUERYSMITH_LLM_API_KEY` and `QUERYSMITH_LLM_BASE_URL` names.

### OpenAI

For the OpenAI API, configure its key and explicitly set the OpenAI-compatible endpoint:

```dotenv
OPENAI_API_KEY=your-openai-api-key
QUERYSMITH_LLM_BASE_URL=https://api.openai.com/v1
QUERYSMITH_LLM_MODEL=gpt-4o-mini
```

Do not place actual credentials in source files, documentation, or commits.

## Minimal working example

```python
from querysmith import load_config, make_engine
from querysmith.llm import OpenAICompatibleClient
from querysmith.pipeline import generate_query

config = load_config()
engine = make_engine(config)
client = OpenAICompatibleClient()

sql = generate_query(
    question="Show the top 10 customers by total order value.",
    engine=engine,
    client=client,
    schema="dbo",
)
print(sql)
```

The same flow accepts Persian questions, for example: `ده مشتری با بیشترین مبلغ سفارش را نمایش بده.`

To execute a generated query, pass it to `querysmith.pipeline.execute_select(engine, sql)`. That function validates the SQL again and returns at most 100 rows by default (up to 1,000 when requested).

## Security model

QuerySmith treats generated SQL as untrusted input. Before generation, it supplies the LLM with the introspected schema. Before execution, its application-level guard permits only a single conservative `SELECT` or `WITH ... SELECT` query and rejects comments, multiple statements, DDL/DML keywords, procedure access, `SELECT INTO`, `OUTPUT INTO`, risky external data access, and linked-server-style names.

These checks reduce risk; they are not a complete security boundary. Use a read-only SQL Server account that can access only the necessary databases, schemas, tables, and views. In sensitive environments, review generated SQL and add authentication, authorization, rate limiting, logging, and query-cost controls before exposing QuerySmith to untrusted users.

## Limitations

- Supports Microsoft SQL Server and T-SQL only.
- Generates and executes `SELECT` queries only.
- Requires access to an external OpenAI-compatible LLM service.
- SQL quality depends on the schema metadata, question clarity, and selected model.
- Complex or ambiguous questions can produce incorrect or inefficient queries.
- Database permissions and query-resource limits must be managed independently.

## Development and testing

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

## License

QuerySmith is released under the MIT License. See [LICENSE](LICENSE) for details.
