# QuerySmith

QuerySmith is a Python library foundation for converting Persian/English natural language requests into safe SQL Server `SELECT` queries by combining database schema metadata, guardrails, and language model orchestration.

## Local Prototype

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -U pip
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install -e .
Copy-Item .env.example .env
```

Fill the database and LLM values in `.env`, edit `QUESTION` in `main.py`, then run:

```powershell
.venv\Scripts\python main.py
```
