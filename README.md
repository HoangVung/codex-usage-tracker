# Codex Usage Tracker

Local Codex plugin and dashboard for tracking aggregate token usage from Codex session logs.

## What It Does

- Reads local Codex JSONL logs from `~/.codex/sessions/**/*.jsonl`.
- Optionally includes `~/.codex/archived_sessions/*.jsonl`.
- Stores aggregate-only usage metrics in local SQLite.
- Exposes MCP tools for refresh, summaries, session detail, lazy call context, CSV export, and dashboard generation.
- Generates a static hoverable dashboard with flat calls and threaded-by-thread views.
- Can serve the dashboard from localhost so raw logged context is loaded only after a row action.
- Provides a read-only doctor command for local plugin/MCP setup checks.
- Optionally estimates costs from a local pricing file that can be refreshed from OpenAI's published pricing docs.
- Tracks aggregate subagent metadata, including explicit parent session ids when Codex logs them.

The tracker intentionally does not store prompts, assistant messages, tool outputs, pasted secrets, or raw transcript snippets in SQLite, CSV exports, or generated dashboard HTML. The optional localhost server can read redacted, size-limited context from the original JSONL file on demand.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ".[dev]"
```

## Usage

Refresh the local aggregate index:

```bash
codex-usage-tracker refresh
```

Check setup:

```bash
codex-usage-tracker doctor
```

Generate the local dashboard:

```bash
codex-usage-tracker dashboard --open
codex-usage-tracker open-dashboard
```

The dashboard opens in the flat Calls view sorted newest-first. Use the Calls/Threads toggle to group filtered usage by thread, with the most recently active thread at the top by default. Click a column header such as Time, Thread, Model, Effort, Tokens, Cost, Cache, or Signals to sort that view; clicking the same header toggles direction. Click a thread row to expand its calls in chronological order. Spawned subagents with a logged parent session are attached to that parent thread. Guardian `codex-auto-review` sessions do not currently log a parent session id, so the dashboard attaches them to the nearest named thread with the same cwd and marks that attachment as inferred.

Serve the dashboard with lazy raw-context loading:

```bash
codex-usage-tracker serve-dashboard --open
```

When served this way, each call detail panel gets a `Load context` action. Pressing it fetches only that call's logged turn context from the original local JSONL source. Tool output is omitted by default; the `Include tool output` action loads redacted, size-limited tool output for that call. None of this raw context is written to SQLite, CSV, or the generated HTML.

Show a summary:

```bash
codex-usage-tracker summary --group-by model
codex-usage-tracker summary --group-by thread --limit 20
codex-usage-tracker summary --preset today
codex-usage-tracker summary --preset last-7-days
codex-usage-tracker summary --preset expensive
codex-usage-tracker summary --preset by-subagent-role
codex-usage-tracker expensive --limit 10
codex-usage-tracker pricing-coverage
```

Show one session:

```bash
codex-usage-tracker session <session-id>
```

Load one call's logged context on demand:

```bash
codex-usage-tracker context <record-id>
```

Export CSV:

```bash
codex-usage-tracker export --output usage.csv
```

Enable optional cost estimates:

```bash
codex-usage-tracker update-pricing
```

This fetches OpenAI text-token pricing from `https://developers.openai.com/api/docs/pricing.md`, parses the selected tier, and writes a source-stamped local cache to `~/.codex-usage-tracker/pricing.json`. The default tier is `standard`; other supported tiers are `batch`, `flex`, and `priority`. If a pricing file already exists, the updater leaves a timestamped `.bak` copy next to it before replacing the active cache.

The updater also includes a marked best-guess estimate for Codex's internal `codex-auto-review` label. OpenAI does not publish a pricing row for that internal model name, so the estimate uses OpenAI's published `codex-mini-latest` Codex pricing from `https://openai.com/index/introducing-codex/`: `$1.50` per 1M input tokens, a 75% prompt-cache discount (`$0.375` per 1M cached input tokens), and `$6.00` per 1M output tokens. Use `--no-estimates` when you want only pricing rows parsed from the OpenAI pricing table.

For a manual template instead:

```bash
codex-usage-tracker init-pricing
```

Edit `~/.codex-usage-tracker/pricing.json` with USD-per-million-token rates for any local overrides or models that are not present in the OpenAI pricing table. Normal reports never contact the network; only `update-pricing` refreshes the local pricing cache.

## Install As A Local Codex Plugin

After installing the Python package in the repo-local `.venv`, register the plugin locally:

```bash
python scripts/install_local_plugin.py
```

Restart Codex after registration so it can discover the plugin. The installer symlinks this repo into `~/plugins/codex-usage-tracker` and updates `~/.agents/plugins/marketplace.json` without removing existing entries.

## MCP Tools

- `refresh_usage_index`
- `usage_doctor`
- `usage_summary`
- `session_usage`
- `usage_call_context`
- `most_expensive_usage_calls`
- `usage_pricing_coverage`
- `generate_usage_dashboard`
- `export_usage_csv`
- `init_usage_pricing_config`
- `update_usage_pricing_config`

## Data Privacy

The SQLite database is stored at `~/.codex-usage-tracker/usage.sqlite3` by default and contains only aggregate metrics:

- session id, thread name, cwd, source file, turn id, timestamps
- model, reasoning effort, context window
- token counts and derived efficiency ratios
- subagent source, role, nickname, and parent session id when present

Raw chat text and tool outputs are ignored by the parser and are never written to the tracker database, CSV exports, or generated dashboard HTML. `usage_call_context`, `codex-usage-tracker context`, and the `serve-dashboard` context endpoint read a single source JSONL file only when explicitly requested, redact common secret patterns, and cap returned text size.

Cost estimates are calculated only from aggregate token fields and your local pricing config. They are omitted when no matching model price is configured. Pricing refreshes pull only OpenAI's public pricing markdown and do not send local usage data anywhere.

## Test

```bash
python -m pytest
python -m compileall src
codex-usage-tracker update-pricing --output /tmp/codex-usage-pricing.json
codex-usage-tracker doctor
codex-usage-tracker dashboard --output /tmp/codex-usage-dashboard.html
codex-usage-tracker serve-dashboard --help
codex-usage-tracker pricing-coverage
codex-usage-tracker summary --preset by-subagent-role
codex-usage-tracker expensive --limit 5
```
