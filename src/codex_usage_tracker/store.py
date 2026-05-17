"""SQLite persistence and aggregate queries for Codex usage data."""

from __future__ import annotations

import csv
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from codex_usage_tracker.models import RefreshResult, UsageEvent
from codex_usage_tracker.parser import (
    find_session_logs,
    load_session_index,
    parse_usage_events,
)
from codex_usage_tracker.paths import DEFAULT_CODEX_HOME, DEFAULT_DB_PATH


EVENT_COLUMNS = [
    "record_id",
    "session_id",
    "thread_name",
    "session_updated_at",
    "event_timestamp",
    "source_file",
    "line_number",
    "turn_id",
    "turn_timestamp",
    "cwd",
    "model",
    "effort",
    "current_date",
    "timezone",
    "thread_source",
    "subagent_type",
    "agent_role",
    "agent_nickname",
    "parent_session_id",
    "model_context_window",
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
    "cumulative_input_tokens",
    "cumulative_cached_input_tokens",
    "cumulative_output_tokens",
    "cumulative_reasoning_output_tokens",
    "cumulative_total_tokens",
    "uncached_input_tokens",
    "cache_ratio",
    "reasoning_output_ratio",
    "context_window_percent",
]


def refresh_usage_index(
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
) -> RefreshResult:
    """Scan Codex logs and upsert aggregate usage events."""

    logs = find_session_logs(codex_home=codex_home, include_archived=include_archived)
    session_index = load_session_index(codex_home)
    events = parse_usage_events(logs, session_index=session_index)
    inserted = upsert_usage_events(events, db_path=db_path)
    return RefreshResult(
        scanned_files=len(logs),
        parsed_events=len(events),
        inserted_or_updated_events=inserted,
        db_path=str(db_path),
    )


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
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
            uncached_input_tokens INTEGER NOT NULL,
            cache_ratio REAL NOT NULL,
            reasoning_output_ratio REAL NOT NULL,
            context_window_percent REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS refresh_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_usage_session ON usage_events(session_id);
        CREATE INDEX IF NOT EXISTS idx_usage_timestamp ON usage_events(event_timestamp);
        CREATE INDEX IF NOT EXISTS idx_usage_model_effort ON usage_events(model, effort);
        CREATE INDEX IF NOT EXISTS idx_usage_thread ON usage_events(thread_name);
        """
    )
    _ensure_columns(
        conn,
        {
            "thread_source": "TEXT",
            "subagent_type": "TEXT",
            "agent_role": "TEXT",
            "agent_nickname": "TEXT",
            "parent_session_id": "TEXT",
        },
    )


def _ensure_columns(conn: sqlite3.Connection, columns: dict[str, str]) -> None:
    existing = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(usage_events)").fetchall()
    }
    for column, column_type in columns.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE usage_events ADD COLUMN {column} {column_type}")


def upsert_usage_events(
    events: Iterable[UsageEvent], db_path: Path = DEFAULT_DB_PATH
) -> int:
    rows = [event.to_row() for event in events]
    with connect(db_path) as conn:
        init_db(conn)
        if not rows:
            return 0
        placeholders = ", ".join("?" for _ in EVENT_COLUMNS)
        update_clause = ", ".join(
            f"{column}=excluded.{column}"
            for column in EVENT_COLUMNS
            if column != "record_id"
        )
        sql = (
            f"INSERT INTO usage_events ({', '.join(EVENT_COLUMNS)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT(record_id) DO UPDATE SET {update_clause}"
        )
        conn.executemany(sql, [[row[column] for column in EVENT_COLUMNS] for row in rows])
        return len(rows)


def query_summary(
    db_path: Path = DEFAULT_DB_PATH,
    group_by: str = "thread",
    limit: int = 20,
    since: str | None = None,
) -> list[dict[str, Any]]:
    group_expr = _group_expression(group_by)
    where_clause, params = _since_where_clause(since)
    sql = f"""
        SELECT
            {group_expr} AS group_key,
            COUNT(*) AS model_calls,
            COUNT(DISTINCT session_id) AS sessions,
            COUNT(DISTINCT turn_id) AS turns,
            SUM(input_tokens) AS input_tokens,
            SUM(cached_input_tokens) AS cached_input_tokens,
            SUM(uncached_input_tokens) AS uncached_input_tokens,
            SUM(output_tokens) AS output_tokens,
            SUM(reasoning_output_tokens) AS reasoning_output_tokens,
            SUM(total_tokens) AS total_tokens,
            AVG(cache_ratio) AS avg_cache_ratio,
            AVG(reasoning_output_ratio) AS avg_reasoning_output_ratio,
            AVG(context_window_percent) AS avg_context_window_percent,
            MAX(event_timestamp) AS latest_event
        FROM usage_events
        {where_clause}
        GROUP BY group_key
        ORDER BY total_tokens DESC
        LIMIT ?
    """
    params.append(limit)
    with connect(db_path) as conn:
        init_db(conn)
        return [_row_to_dict(row) for row in conn.execute(sql, params)]


def query_session_usage(
    db_path: Path = DEFAULT_DB_PATH,
    session_id: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        init_db(conn)
        if session_id is None:
            row = conn.execute(
                """
                SELECT session_id
                FROM usage_events
                GROUP BY session_id
                ORDER BY MAX(event_timestamp) DESC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return []
            session_id = str(row["session_id"])
        rows = conn.execute(
            """
            SELECT *
            FROM usage_events
            WHERE session_id = ?
            ORDER BY event_timestamp, cumulative_total_tokens
            LIMIT ?
            """,
            (session_id, limit),
        )
        return [_row_to_dict(row) for row in rows]


def query_dashboard_events(
    db_path: Path = DEFAULT_DB_PATH, limit: int = 5000, since: str | None = None
) -> list[dict[str, Any]]:
    where_clause, params = _since_where_clause(since)
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            f"""
            SELECT *
            FROM usage_events
            {where_clause}
            ORDER BY event_timestamp DESC, cumulative_total_tokens DESC
            LIMIT ?
            """,
            (*params, limit),
        )
        return [_row_to_dict(row) for row in rows]


def query_most_expensive_calls(
    db_path: Path = DEFAULT_DB_PATH, limit: int = 20, since: str | None = None
) -> list[dict[str, Any]]:
    """Return the largest aggregate model calls by last-call token count."""

    where_clause, params = _since_where_clause(since)
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            f"""
            SELECT *
            FROM usage_events
            {where_clause}
            ORDER BY total_tokens DESC, event_timestamp DESC
            LIMIT ?
            """,
            (*params, limit),
        )
        return [_row_to_dict(row) for row in rows]


def export_usage_csv(
    output_path: Path, db_path: Path = DEFAULT_DB_PATH, limit: int | None = None
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sql = "SELECT * FROM usage_events ORDER BY event_timestamp, cumulative_total_tokens"
    params: tuple[int, ...] = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (limit,)
    with connect(db_path) as conn:
        init_db(conn)
        rows = [_row_to_dict(row) for row in conn.execute(sql, params)]

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVENT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column) for column in EVENT_COLUMNS})
    return len(rows)


def _group_expression(group_by: str) -> str:
    mapping = {
        "date": "substr(event_timestamp, 1, 10)",
        "model": "coalesce(model, 'Unknown model')",
        "effort": "coalesce(effort, 'Unknown effort')",
        "cwd": "coalesce(cwd, 'Unknown cwd')",
        "thread": "coalesce(thread_name, session_id)",
        "session": "session_id",
        "thread_source": "coalesce(thread_source, 'user')",
        "subagent_type": "coalesce(subagent_type, 'not subagent')",
        "agent_role": "coalesce(agent_role, 'not agent role')",
        "parent_session": "coalesce(parent_session_id, 'no parent session')",
    }
    try:
        return mapping[group_by]
    except KeyError as exc:
        allowed = ", ".join(sorted(mapping))
        raise ValueError(f"group_by must be one of: {allowed}") from exc


def _since_where_clause(since: str | None) -> tuple[str, list[str]]:
    if not since:
        return "", []
    return "WHERE event_timestamp >= ?", [since]


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}
