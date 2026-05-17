# Codex Usage Tracker Instructions

## Project Purpose

This repo builds a local Codex plugin and dashboard that track aggregate token usage from Codex session logs.

## Tech Stack

- Python 3.10+
- SQLite via the Python standard library
- MCP Python SDK for Codex tool exposure
- Pytest for tests

## Repo Layout

- `src/codex_usage_tracker/` - parser, SQLite store, reports, dashboard, CLI, and MCP server.
- `.codex-plugin/plugin.json` - Codex plugin manifest.
- `.mcp.json` - MCP server configuration for Codex.
- `scripts/install_local_plugin.py` - local plugin registration script.
- `tests/` - synthetic fixtures and unit tests.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Validation

```bash
python -m pytest
python -m compileall src
codex-usage-tracker dashboard --output /tmp/codex-usage-dashboard.html
```

## Privacy Rules

- Never commit real Codex session logs.
- Never store raw prompts, assistant text, tool outputs, pasted secrets, or message snippets.
- Keep fixture data synthetic.
- Keep local SQLite databases, CSV exports, HTML dashboards, caches, and virtualenvs out of git.

## Definition Of Done

- Parser handles synthetic session logs without reading raw message content.
- SQLite refresh is idempotent.
- MCP tool functions return concise aggregate data.
- Dashboard is generated from aggregate-only JSON.
- Tests and compile checks pass.
