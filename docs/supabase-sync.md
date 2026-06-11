# Supabase Online Sync

Codex Usage Tracker supports online sync via a self-hosted or cloud Supabase instance. This allows multiple machines to share a merged view of aggregate model usage.

> [!CAUTION]
> **Security Warning**: 
> - **NEVER** use the `service_role` key in this local configuration. The `service_role` key bypasses all Row Level Security (RLS) policies and would allow anyone with access to the local config file to read, modify, or delete all data in the database.
> - Always use the public **`anon` key** combined with Row Level Security (RLS) policies.
> - **NEVER** commit `~/.codex-usage-tracker/sync.json` to public version control, as it contains your project credentials. Add it to your global `.gitignore`.

## Supabase PostgreSQL Schema

To set up online sync, run the following SQL commands in your Supabase SQL Editor to create the required table, enable Row Level Security, and configure security policies:

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
    "current_date" TEXT,
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

-- Enable Row Level Security (RLS)
ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY;

-- Policy 1: Allow public anonymous insertion of usage events matching a specific workspace ID
CREATE POLICY "Allow anon insert by workspace" ON usage_events
    FOR INSERT
    TO anon
    WITH CHECK (workspace_id = 'your-workspace-id');

-- Policy 2: Allow select access for anonymous users to query events matching a specific workspace ID
CREATE POLICY "Allow anon select by workspace" ON usage_events
    FOR SELECT
    TO anon
    USING (workspace_id = 'your-workspace-id');

-- Policy 3: Allow update/upsert for anonymous users matching a specific workspace ID
CREATE POLICY "Allow anon update by workspace" ON usage_events
    FOR UPDATE
    TO anon
    USING (workspace_id = 'your-workspace-id')
    WITH CHECK (workspace_id = 'your-workspace-id');
```
> [!WARNING]
> **Important Note on Workspace RLS Policies**:
> The static workspace policies above (`workspace_id = 'your-workspace-id'`) are intended only for private, personal, or trusted internal environment syncs where simple segregation is needed. Anyone who inspects the local configuration or queries the public API can easily spoof the `workspace_id`.
> 
> For multi-tenant, multi-user, or production team deployments, you should integrate **Supabase Auth** and utilize `auth.uid()` or validated JWT claims (e.g. via custom headers or claims mapping) inside your RLS policies instead of relying on a raw static string check.

> [!NOTE]
> The table structure matches the local SQLite schema but adds a `device_id` to attribute the source machine, a `workspace_id` to isolate projects, and a `synced_at` timestamp. It does not store raw prompts, assistant messages, tool output, or transcript snippets.

## Config Local Setup

Create or initialize your sync config at `~/.codex-usage-tracker/sync.json`.

```bash
codex-usage-tracker sync init
```

The init wizard will prompt you for:
1. **Supabase URL**: Your Supabase project REST endpoint (e.g. `https://your-project.supabase.co`)
2. **Supabase Key**: Your public **`anon` key**.
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
