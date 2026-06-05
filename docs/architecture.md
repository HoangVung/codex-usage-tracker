# Architecture

Codex Usage Tracker is a local sidecar app. It reads aggregate token counters from Codex session JSONL logs, stores only aggregate metrics in SQLite, and exposes those metrics through CLI commands, MCP tools, CSV export, and a static or localhost-served dashboard.

## Boundaries

- `parser.py` converts local JSONL events into aggregate `UsageEvent` records. It must not persist prompts, assistant text, tool output, or transcript snippets.
- `schema.py` owns persisted `usage_events` columns. Add columns there before changing SQLite migrations or export behavior.
- `store.py` owns SQLite setup, refresh, rebuild, and query access. Keep filesystem scanning and database writes here.
- `reports.py` is the application-service layer for summaries, expensive-call reports, pricing coverage, and filtered query payloads. CLI and MCP should call this layer instead of duplicating report assembly.
- `api_payloads.py` owns stable JSON payload helpers shared by CLI and MCP. Add schema-versioned payload builders here when both surfaces need the same shape.
- `costing.py`, `pricing_config.py`, `pricing_openai.py`, `pricing_estimates.py`, and `allowance.py` own cost, credit, rate-card, and allowance annotation. Keep estimate confidence and source metadata attached to rows.
- `projects.py`, `threads.py`, and `recommendations.py` annotate aggregate rows with project identity, thread relationships, and actionable signals.
- `dashboard.py` builds aggregate-only dashboard payloads and writes HTML/assets. `server.py` adds localhost refresh and explicit lazy context loading.
- `context.py` is the only normal path that reads raw log context, and it does so only for one selected record on demand with redaction and size limits.
- `plugin_installer.py`, `.mcp.json`, `skills/`, and `scripts/check_release.py` own install and packaging behavior.

## Extension Rules

1. Add new persisted metrics through `UsageEvent`, `schema.py`, migrations, store queries, dashboard payload tests, and CSV/export checks.
2. Add new report views through `reports.py` first, then wire CLI and MCP wrappers to that shared service.
3. Add new machine-readable outputs through `api_payloads.py` or report payload methods with a `schema` value and focused tests.
4. Add dashboard-only interactions in `plugin_data/dashboard/dashboard.js` and keep URL state in `dashboard_state.js`.
5. Keep all examples, screenshots, mocks, and tests synthetic. Never derive fixtures from real logs.

## Validation

Use the narrowest useful check first, then the release suite before committing:

```bash
python -m pytest
python -m compileall src
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard.js
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_state.js
python scripts/check_release.py
python -m build
python scripts/check_release.py --dist
git diff --check
```

Dashboard UI changes should also be opened in a browser and checked on desktop and mobile widths for overlap, stale state, and aggregate-only output.
