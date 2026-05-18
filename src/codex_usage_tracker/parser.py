"""Parse Codex JSONL session logs into aggregate usage records."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, MutableMapping
from pathlib import Path
from typing import Any

from codex_usage_tracker.models import SessionInfo, UsageEvent
from codex_usage_tracker.paths import DEFAULT_CODEX_HOME

SESSION_ID_RE = re.compile(
    r"rollout-[^-]+-[0-9T:-]+-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$"
)


def load_session_index(codex_home: Path = DEFAULT_CODEX_HOME) -> dict[str, SessionInfo]:
    """Load Codex thread names without reading transcript content."""

    index_path = codex_home / "session_index.jsonl"
    sessions: dict[str, SessionInfo] = {}
    if not index_path.exists():
        return sessions

    with index_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            session_id = payload.get("id")
            if not isinstance(session_id, str):
                continue
            sessions[session_id] = SessionInfo(
                session_id=session_id,
                thread_name=_optional_str(payload.get("thread_name")),
                updated_at=_optional_str(payload.get("updated_at")),
            )
    return sessions


def find_session_logs(
    codex_home: Path = DEFAULT_CODEX_HOME, include_archived: bool = False
) -> list[Path]:
    """Find local Codex JSONL logs."""

    paths = list((codex_home / "sessions").glob("**/*.jsonl"))
    if include_archived:
        paths.extend((codex_home / "archived_sessions").glob("*.jsonl"))
    return sorted(path for path in paths if path.is_file())


def parse_usage_events(
    paths: Iterable[Path],
    session_index: dict[str, SessionInfo] | None = None,
    stats: MutableMapping[str, int] | None = None,
) -> list[UsageEvent]:
    """Parse all provided logs into aggregate usage events."""

    index = session_index or {}
    events: list[UsageEvent] = []
    for path in paths:
        events.extend(parse_usage_events_from_file(path, index, stats=stats))
    return events


def parse_usage_events_from_file(
    path: Path,
    session_index: dict[str, SessionInfo] | None = None,
    stats: MutableMapping[str, int] | None = None,
) -> list[UsageEvent]:
    """Parse one Codex JSONL log without storing raw message content."""

    index = session_index or {}
    file_session_id = _session_id_from_path(path)
    session_id = file_session_id
    session_info = index.get(session_id) if session_id else None
    current_turn: dict[str, Any] = {}
    session_meta: dict[str, str | None] = {}
    last_cumulative_total = -1
    events: list[UsageEvent] = []

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                envelope = json.loads(line)
            except json.JSONDecodeError:
                continue

            payload = envelope.get("payload")
            if not isinstance(payload, dict):
                continue

            entry_type = envelope.get("type")
            timestamp = _optional_str(envelope.get("timestamp")) or ""

            if entry_type == "session_meta":
                if not session_id:
                    session_id = _optional_str(payload.get("id"))
                    session_info = index.get(session_id or "")
                session_meta = _session_metadata(payload, index)
                continue

            if entry_type == "turn_context":
                current_turn = {
                    "turn_id": _optional_str(payload.get("turn_id")),
                    "turn_timestamp": timestamp,
                    "cwd": _optional_str(payload.get("cwd")),
                    "model": _optional_str(payload.get("model")),
                    "effort": _optional_str(payload.get("effort")),
                    "current_date": _optional_str(payload.get("current_date")),
                    "timezone": _optional_str(payload.get("timezone")),
                }
                continue

            if entry_type != "event_msg" or payload.get("type") != "token_count":
                continue

            info = payload.get("info")
            if not isinstance(info, dict):
                continue

            total_usage = info.get("total_token_usage")
            last_usage = info.get("last_token_usage")
            if not isinstance(total_usage, dict) or not isinstance(last_usage, dict):
                continue

            try:
                cumulative_total = _required_int(total_usage.get("total_tokens"))
            except ValueError:
                _increment_stat(stats, "skipped_events")
                continue
            if cumulative_total <= last_cumulative_total:
                continue

            effective_session_id = session_id or "unknown"
            session_info = session_info or index.get(effective_session_id)
            try:
                event = _build_event(
                    path=path,
                    line_number=line_number,
                    event_timestamp=timestamp,
                    session_id=effective_session_id,
                    session_info=session_info,
                    session_meta=session_meta,
                    current_turn=current_turn,
                    model_context_window=_nullable_int(info.get("model_context_window")),
                    last_usage=last_usage,
                    total_usage=total_usage,
                )
            except ValueError:
                _increment_stat(stats, "skipped_events")
                continue
            last_cumulative_total = cumulative_total
            events.append(event)

    return events


def _build_event(
    path: Path,
    line_number: int,
    event_timestamp: str,
    session_id: str,
    session_info: SessionInfo | None,
    session_meta: dict[str, str | None],
    current_turn: dict[str, Any],
    model_context_window: int | None,
    last_usage: dict[str, Any],
    total_usage: dict[str, Any],
) -> UsageEvent:
    input_tokens = _required_int(last_usage.get("input_tokens"))
    cached_input_tokens = _required_int(last_usage.get("cached_input_tokens"))
    output_tokens = _required_int(last_usage.get("output_tokens"))
    reasoning_output_tokens = _required_int(last_usage.get("reasoning_output_tokens"))
    total_tokens = _required_int(last_usage.get("total_tokens"))
    cumulative_total_tokens = _required_int(total_usage.get("total_tokens"))
    record_id = _record_id(
        session_id=session_id,
        turn_id=_optional_str(current_turn.get("turn_id")),
        event_timestamp=event_timestamp,
        cumulative_total_tokens=cumulative_total_tokens,
        total_tokens=total_tokens,
    )
    return UsageEvent(
        record_id=record_id,
        session_id=session_id,
        thread_name=session_info.thread_name if session_info else None,
        session_updated_at=session_info.updated_at if session_info else None,
        event_timestamp=event_timestamp,
        source_file=str(path),
        line_number=line_number,
        turn_id=_optional_str(current_turn.get("turn_id")),
        turn_timestamp=_optional_str(current_turn.get("turn_timestamp")),
        cwd=_optional_str(current_turn.get("cwd")),
        model=_optional_str(current_turn.get("model")),
        effort=_optional_str(current_turn.get("effort")),
        current_date=_optional_str(current_turn.get("current_date")),
        timezone=_optional_str(current_turn.get("timezone")),
        thread_source=session_meta.get("thread_source"),
        subagent_type=session_meta.get("subagent_type"),
        agent_role=session_meta.get("agent_role"),
        agent_nickname=session_meta.get("agent_nickname"),
        parent_session_id=session_meta.get("parent_session_id"),
        parent_thread_name=session_meta.get("parent_thread_name"),
        parent_session_updated_at=session_meta.get("parent_session_updated_at"),
        model_context_window=model_context_window,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_output_tokens=reasoning_output_tokens,
        total_tokens=total_tokens,
        cumulative_input_tokens=_required_int(total_usage.get("input_tokens")),
        cumulative_cached_input_tokens=_required_int(total_usage.get("cached_input_tokens")),
        cumulative_output_tokens=_required_int(total_usage.get("output_tokens")),
        cumulative_reasoning_output_tokens=_required_int(
            total_usage.get("reasoning_output_tokens")
        ),
        cumulative_total_tokens=cumulative_total_tokens,
    )


def _session_metadata(
    payload: dict[str, Any],
    session_index: dict[str, SessionInfo],
) -> dict[str, str | None]:
    source = payload.get("source")
    metadata: dict[str, str | None] = {
        "thread_source": _optional_str(payload.get("thread_source")),
        "subagent_type": None,
        "agent_role": None,
        "agent_nickname": None,
        "parent_session_id": None,
        "parent_thread_name": None,
        "parent_session_updated_at": None,
    }
    if not isinstance(source, dict):
        return metadata

    subagent = source.get("subagent")
    if not isinstance(subagent, dict):
        return metadata

    other = _optional_str(subagent.get("other"))
    if other:
        metadata["subagent_type"] = other
        return metadata

    thread_spawn = subagent.get("thread_spawn")
    if isinstance(thread_spawn, dict):
        metadata["subagent_type"] = "thread_spawn"
        metadata["agent_role"] = _optional_str(thread_spawn.get("agent_role"))
        metadata["agent_nickname"] = _optional_str(thread_spawn.get("agent_nickname"))
        parent_session_id = _optional_str(thread_spawn.get("parent_thread_id"))
        metadata["parent_session_id"] = parent_session_id
        if parent_session_id:
            parent_info = session_index.get(parent_session_id)
            if parent_info:
                metadata["parent_thread_name"] = parent_info.thread_name
                metadata["parent_session_updated_at"] = parent_info.updated_at
    return metadata


def _record_id(
    session_id: str,
    turn_id: str | None,
    event_timestamp: str,
    cumulative_total_tokens: int,
    total_tokens: int,
) -> str:
    raw = "|".join(
        [
            session_id,
            turn_id or "",
            event_timestamp,
            str(cumulative_total_tokens),
            str(total_tokens),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _session_id_from_path(path: Path) -> str | None:
    match = SESSION_ID_RE.search(path.name)
    if not match:
        return None
    return match.group(1)


def _optional_str(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _nullable_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return _int(value)
    except ValueError:
        return None


def _int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"invalid integer value: {value!r}") from exc
    return 0


def _required_int(value: object) -> int:
    if value is None:
        return 0
    return _int(value)


def _increment_stat(stats: MutableMapping[str, int] | None, key: str) -> None:
    if stats is not None:
        stats[key] = stats.get(key, 0) + 1
