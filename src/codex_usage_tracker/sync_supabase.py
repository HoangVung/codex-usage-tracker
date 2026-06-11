"""Supabase online sync module for Codex Usage Tracker."""

from __future__ import annotations

import json
import urllib.request
import urllib.error
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from codex_usage_tracker.paths import APP_DIR

DEFAULT_SYNC_PATH = APP_DIR / "sync.json"


class SyncConfig:
    """Supabase sync configuration."""

    def __init__(
        self,
        path: Path = DEFAULT_SYNC_PATH,
        supabase_url: str = "",
        supabase_key: str = "",
        workspace_id: str = "",
        device_id: str = "",
        auto_on_refresh: bool = False,
        privacy_mode: str = "strict",
        loaded: bool = False,
        error: Optional[str] = None,
    ) -> None:
        self.path = path
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key
        self.workspace_id = workspace_id
        self.device_id = device_id or str(uuid.uuid4())
        self.auto_on_refresh = auto_on_refresh
        self.privacy_mode = privacy_mode
        self.loaded = loaded
        self.error = error

    def save(self) -> None:
        """Write current config back to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "supabase_url": self.supabase_url,
            "supabase_key": self.supabase_key,
            "workspace_id": self.workspace_id,
            "device_id": self.device_id,
            "auto_on_refresh": self.auto_on_refresh,
            "privacy_mode": self.privacy_mode,
        }
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_sync_config(path: Path = DEFAULT_SYNC_PATH) -> SyncConfig:
    """Load Supabase sync config from sync.json."""
    path = path.expanduser()
    if not path.exists():
        return SyncConfig(path=path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return SyncConfig(path=path, error=str(exc))

    if not isinstance(data, dict):
        return SyncConfig(path=path, error="Config must be a JSON object")

    return SyncConfig(
        path=path,
        supabase_url=data.get("supabase_url", ""),
        supabase_key=data.get("supabase_key", ""),
        workspace_id=data.get("workspace_id", ""),
        device_id=data.get("device_id", ""),
        auto_on_refresh=data.get("auto_on_refresh", False),
        privacy_mode=data.get("privacy_mode", "strict"),
        loaded=True,
    )


def _supabase_request(
    url: str,
    key: str,
    method: str,
    path: str,
    payload: Optional[Any] = None,
    query_params: Optional[dict[str, str]] = None,
    headers: Optional[dict[str, str]] = None,
) -> Any:
    """Make an HTTP request to Supabase REST API using Python's stdlib."""
    if not url or not key:
        raise ValueError("Supabase URL and API key must be configured")

    url_parts = urllib.parse.urlparse(url)
    full_path = f"/rest/v1/{path.lstrip('/')}"

    full_url = urllib.parse.urlunparse((
        url_parts.scheme,
        url_parts.netloc,
        full_path,
        "",
        urllib.parse.urlencode(query_params) if query_params else "",
        ""
    ))

    req_headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }
    if headers:
        req_headers.update(headers)

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        full_url,
        data=data,
        headers=req_headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = response.read().decode("utf-8")
            if res_data:
                return json.loads(res_data)
            return None
    except urllib.error.HTTPError as exc:
        err_msg = exc.read().decode("utf-8")
        raise RuntimeError(f"Supabase HTTP error {exc.code}: {err_msg}") from exc
    except Exception as exc:
        raise RuntimeError(f"Supabase request failed: {exc}") from exc


def query_local_events_for_sync(
    db_path: Path,
    since: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Query local events from the SQLite database."""
    from codex_usage_tracker.store import connect, init_db

    query = "SELECT * FROM usage_events"
    params: list[Any] = []
    if since:
        query += " WHERE event_timestamp >= ?"
        params.append(since)

    query += " ORDER BY event_timestamp DESC"
    if limit is not None and limit > 0:
        query += " LIMIT ?"
        params.append(limit)

    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def merge_remote_events(
    db_path: Path,
    remote_rows: list[dict[str, Any]],
    local_device_id: str,
) -> int:
    """Idempotently merge remote rows into local SQLite DB, keeping local fidelity."""
    from codex_usage_tracker.store import connect, init_db
    from codex_usage_tracker.schema import USAGE_EVENT_COLUMN_NAMES

    if not remote_rows:
        return 0

    inserted_or_updated = 0
    with connect(db_path) as conn:
        init_db(conn)

        existing = {
            str(row["record_id"]): str(row["device_id"]) if row["device_id"] else ""
            for row in conn.execute("SELECT record_id, device_id FROM usage_events").fetchall()
        }

        EVENT_COLUMNS = list(USAGE_EVENT_COLUMN_NAMES)
        placeholders = ", ".join("?" for _ in EVENT_COLUMNS)
        update_clause = ", ".join(
            f"{column}=excluded.{column}"
            for column in EVENT_COLUMNS
            if column != "record_id"
        )
        sql_upsert = (
            f"INSERT INTO usage_events ({', '.join(EVENT_COLUMNS)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT(record_id) DO UPDATE SET {update_clause}"
        )

        to_upsert = []
        for row in remote_rows:
            record_id = str(row.get("record_id", ""))
            remote_device_id = str(row.get("device_id") or "")

            if record_id in existing:
                existing_device_id = existing[record_id]
                # Keep local unredacted row if it is ours
                if existing_device_id == local_device_id:
                    continue
                # If local device_id is empty but remote claims it's ours, set local device_id
                if not existing_device_id and remote_device_id == local_device_id:
                    conn.execute(
                        "UPDATE usage_events SET device_id = ? WHERE record_id = ?",
                        (local_device_id, record_id),
                    )
                    continue

            row_data = []
            for col in EVENT_COLUMNS:
                row_data.append(row.get(col))

            to_upsert.append(row_data)

        if to_upsert:
            conn.executemany(sql_upsert, to_upsert)
            inserted_or_updated = len(to_upsert)

    return inserted_or_updated


def sync_push(
    db_path: Path,
    config: SyncConfig,
    privacy_mode: Optional[str] = None,
    since: Optional[str] = None,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> int:
    """Push local events to Supabase after applying privacy mode."""
    local_rows = query_local_events_for_sync(db_path, since=since, limit=limit)
    if not local_rows:
        return 0

    mode = privacy_mode or config.privacy_mode or "strict"
    if mode == "normal":
        import sys
        print("[WARNING] normal privacy mode is selected for online sync. Local source paths, CWDs, and thread names will be uploaded without redaction.", file=sys.stderr)
    from codex_usage_tracker.projects import apply_project_privacy_to_rows
    redacted_rows = apply_project_privacy_to_rows(local_rows, privacy_mode=mode)

    # Inject device and workspace IDs
    for row in redacted_rows:
        row["device_id"] = config.device_id
        if config.workspace_id:
            row["workspace_id"] = config.workspace_id

    if dry_run:
        return len(redacted_rows)

    headers = {
        "Prefer": "resolution=merge-duplicates",
    }
    _supabase_request(
        url=config.supabase_url,
        key=config.supabase_key,
        method="POST",
        path="usage_events",
        payload=redacted_rows,
        query_params={"on_conflict": "record_id"},
        headers=headers,
    )
    return len(redacted_rows)


def sync_pull(
    db_path: Path,
    config: SyncConfig,
    since: Optional[str] = None,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> int:
    """Pull remote events from Supabase and merge them locally."""
    query_params = {
        "select": "*",
    }
    if config.workspace_id:
        query_params["workspace_id"] = f"eq.{config.workspace_id}"

    if since:
        query_params["event_timestamp"] = f"gte.{since}"

    if limit is not None and limit > 0:
        query_params["limit"] = str(limit)

    query_params["order"] = "event_timestamp.desc"

    remote_rows = _supabase_request(
        url=config.supabase_url,
        key=config.supabase_key,
        method="GET",
        path="usage_events",
        query_params=query_params,
    )

    if not remote_rows:
        return 0

    if dry_run:
        return len(remote_rows)

    return merge_remote_events(db_path, remote_rows, config.device_id)


def record_sync_metadata(
    db_path: Path,
    status: str,
    pushed: int = 0,
    pulled: int = 0,
    error: Optional[str] = None,
) -> None:
    """Save the sync summary info to refresh_meta table."""
    from codex_usage_tracker.store import connect, init_db
    values = {
        "last_sync_status": status,
        "last_sync_pushed": str(pushed),
        "last_sync_pulled": str(pulled),
        "last_sync_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "last_sync_error": error or "",
    }
    with connect(db_path) as conn:
        init_db(conn)
        conn.executemany(
            """
            INSERT INTO refresh_meta (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            values.items(),
        )


def sync_run_auto(db_path: Path, config: SyncConfig) -> dict[str, Any]:
    """Run sync push and pull automatically, recording metadata."""
    try:
        pushed = sync_push(db_path, config)
        pulled = sync_pull(db_path, config)
        record_sync_metadata(db_path, "success", pushed, pulled)
        return {"status": "success", "pushed": pushed, "pulled": pulled}
    except Exception as exc:
        record_sync_metadata(db_path, "failed", error=str(exc))
        import sys
        print(f"[WARN] Supabase sync failed: {exc}", file=sys.stderr)
        return {"status": "failed", "error": str(exc)}
