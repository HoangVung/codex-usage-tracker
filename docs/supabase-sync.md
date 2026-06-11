# Supabase Online Sync

Codex Usage Tracker supports online sync via a self-hosted or cloud Supabase instance. This allows multiple machines to share a merged view of aggregate model usage.

## Supabase PostgreSQL Schema

To set up online sync, run the following SQL commands in your Supabase SQL Editor to create the required table:

```sql
-- Create the usage_events table for aggregate records
CREATE TABLE IF NOT EXISTS usage_events (
    record_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    thread_name TEXT,
    session_updated_at TEXT,
    event_timestamp TEXT NOT NULL,
    source_file TEXT NOT NULL,
    line_number INTEGER NOT NULL,
    turn_id TEXT,
    turn_timestamp TEXT,
    cwd TEXT,
    model TEXT,
    effort TEXT,
    current_date TEXT,
    timezone TEXT,
    thread_source TEXT,
    subagent_type TEXT,
    agent_role TEXT,
    agent_nickname TEXT,
    parent_session_id TEXT,
    parent_thread_name TEXT,
    parent_session_updated_at TEXT,
    model_context_window INTEGER,
    input_tokens INTEGER NOT NULL,
    cached_input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    reasoning_output_tokens INTEGER NOT NULL,
    total_tokens INTEGER NOT NULL,
    cumulative_input_tokens INTEGER NOT NULL,
    cumulative_cached_input_tokens INTEGER NOT NULL,
    cumulative_output_tokens INTEGER NOT NULL,
    cumulative_reasoning_output_tokens INTEGER NOT NULL,
    cumulative_total_tokens INTEGER NOT NULL,
    device_id TEXT,
    workspace_id TEXT,
    uncached_input_tokens INTEGER NOT NULL,
    cache_ratio REAL NOT NULL,
    reasoning_output_ratio REAL NOT NULL,
    context_window_percent REAL NOT NULL,
    synced_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Index for querying and filtering by workspace
CREATE INDEX IF NOT EXISTS usage_events_workspace_idx ON usage_events (workspace_id);
-- Index for ordering by timestamp
CREATE INDEX IF NOT EXISTS usage_events_timestamp_idx ON usage_events (event_timestamp DESC);
```

> [!NOTE]
> The table structure matches the local SQLite schema but adds a `device_id` to attribute the source machine, a `workspace_id` to isolate projects, and a `synced_at` timestamp. It does not store raw prompts, assistant messages, tool output, or transcript snippets.

## Config Local Setup

Create or initialize your sync config at `~/.codex-usage-tracker/sync.json`.
Do not commit this file to Git.

```bash
codex-usage-tracker sync init
```

The init wizard will prompt you for:
1. **Supabase URL**: Your Supabase project REST endpoint (e.g. `https://your-project.supabase.co`)
2. **Supabase Key**: Your anon or service role key.
3. **Workspace ID**: A shared identifier if you want to group multiple devices together (optional).
4. **Auto-sync**: Whether to sync automatically on log refreshes.

Example `sync.json`:

```json
{
  "supabase_url": "https://your-project.supabase.co",
  "supabase_key": "eyJhbGciOi...",
  "workspace_id": "team-workspace-1",
  "device_id": "4a58b6c4-b52f-47dc-913a-ea4c7595e1e0",
  "auto_on_refresh": true,
  "privacy_mode": "strict"
}
```

## Running Sync Commands

### Status

Check the active configuration:

```bash
codex-usage-tracker sync status
```

### Push

Upload local usage events to Supabase:

```bash
codex-usage-tracker sync push
```

- Local rows are sanitized according to your configured `privacy_mode` before upload.
- Uploads default to `strict` or `redacted` mode.

### Pull

Fetch remote rows and merge them into the local SQLite database:

```bash
codex-usage-tracker sync pull
```

- Merging is idempotent and uses the unique `record_id`.
- Rows that originate from the local `device_id` are skipped to ensure that local high-fidelity unredacted data is not overwritten by redacted remote data.

### Run

Run a push followed by a pull:

```bash
codex-usage-tracker sync run
```

## Auto-Sync

When `auto_on_refresh` is `true`, a sync will be performed automatically during:
- `codex-usage-tracker refresh`
- `codex-usage-tracker open-dashboard`
- `codex-usage-tracker serve-dashboard` (and during live aggregate refreshes from the dashboard)

You can temporarily override auto-sync using the `--sync` and `--no-sync` flags:

```bash
# Force sync even if auto_on_refresh is false
codex-usage-tracker refresh --sync

# Skip sync even if auto_on_refresh is true
codex-usage-tracker serve-dashboard --no-sync
```

If Supabase is offline or the network fails, the local refresh and dashboard server will continue to function normally, and a warning will be displayed.
