# Codex Usage Tracker

Local Codex plugin and dashboard for tracking aggregate token usage from Codex session logs.

## What It Does

- Reads local Codex JSONL logs from `~/.codex/sessions/**/*.jsonl`.
- Optionally includes `~/.codex/archived_sessions/*.jsonl`.
- Stores aggregate-only usage metrics in local SQLite.
- Exposes MCP tools for refresh, summaries, session detail, CSV export, and dashboard generation.
- Generates a static hoverable dashboard for local review.

The tracker intentionally does not store prompts, assistant messages, tool outputs, pasted secrets, or raw transcript snippets.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Usage

Refresh the local aggregate index:

```bash
codex-usage-tracker refresh
```

Generate the local dashboard:

```bash
codex-usage-tracker dashboard --open
```

Show a summary:

```bash
codex-usage-tracker summary --group-by model
codex-usage-tracker summary --group-by thread --limit 20
```

Show one session:

```bash
codex-usage-tracker session <session-id>
```

Export CSV:

```bash
codex-usage-tracker export --output usage.csv
```

## Install As A Local Codex Plugin

After installing the Python package in the repo-local `.venv`, register the plugin locally:

```bash
python scripts/install_local_plugin.py
```

Restart Codex after registration so it can discover the plugin. The installer symlinks this repo into `~/plugins/codex-usage-tracker` and updates `~/.agents/plugins/marketplace.json` without removing existing entries.

## MCP Tools

- `refresh_usage_index`
- `usage_summary`
- `session_usage`
- `generate_usage_dashboard`
- `export_usage_csv`

## Data Privacy

The SQLite database is stored at `~/.codex-usage-tracker/usage.sqlite3` by default and contains only aggregate metrics:

- session id, thread name, cwd, source file, turn id, timestamps
- model, reasoning effort, context window
- token counts and derived efficiency ratios

Raw chat text and tool outputs are ignored by the parser and are never written to the tracker database or dashboard.

## Test

```bash
python -m pytest
python -m compileall src
codex-usage-tracker dashboard --output /tmp/codex-usage-dashboard.html
```
