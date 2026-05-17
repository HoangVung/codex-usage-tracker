from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.parser import (
    find_session_logs,
    load_session_index,
    parse_usage_events_from_file,
)

SESSION_ID = "019e374d-c19f-7da3-a44f-8de043a7a64e"


def test_parser_skips_missing_info_and_duplicate_snapshots(tmp_path: Path) -> None:
    log_path = tmp_path / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": SESSION_ID}),
            _entry(
                "session_meta",
                {
                    "id": SESSION_ID,
                    "thread_source": "subagent",
                    "source": {
                        "subagent": {
                            "thread_spawn": {
                                "parent_thread_id": "parent-session",
                                "agent_nickname": "Verifier",
                                "agent_role": "test_runner",
                            }
                        }
                    },
                },
            ),
            _entry(
                "turn_context",
                {
                    "turn_id": "turn-a",
                    "model": "gpt-5.5",
                    "effort": "xhigh",
                    "cwd": "/tmp/work",
                    "current_date": "2026-05-17",
                    "timezone": "America/New_York",
                },
            ),
            _entry("event_msg", {"type": "token_count", "info": None}),
            _token_event(100, 100),
            _entry(
                "response_item",
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "SECRET RAW PROMPT"}],
                },
            ),
            _token_event(100, 100),
            _token_event(150, 50),
            _entry(
                "turn_context",
                {
                    "turn_id": "turn-b",
                    "model": "gpt-5.5",
                    "effort": "high",
                    "cwd": "/tmp/work",
                },
            ),
            _token_event(150, 50),
            _token_event(210, 60),
        ],
    )

    events = parse_usage_events_from_file(log_path, {})

    assert [event.cumulative_total_tokens for event in events] == [100, 150, 210]
    assert [event.total_tokens for event in events] == [100, 50, 60]
    assert events[0].turn_id == "turn-a"
    assert events[-1].turn_id == "turn-b"
    assert events[-1].effort == "high"
    assert events[0].thread_source == "subagent"
    assert events[0].subagent_type == "thread_spawn"
    assert events[0].agent_role == "test_runner"
    assert events[0].agent_nickname == "Verifier"
    assert events[0].parent_session_id == "parent-session"
    assert all("SECRET" not in str(event.to_row()) for event in events)


def test_session_index_join_and_archived_log_discovery(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    session_dir = codex_home / "sessions" / "2026" / "05" / "17"
    archived_dir = codex_home / "archived_sessions"
    session_dir.mkdir(parents=True)
    archived_dir.mkdir(parents=True)
    session_log = session_dir / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    archive_log = archived_dir / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    _write_jsonl(session_log, [_entry("session_meta", {"id": SESSION_ID})])
    _write_jsonl(archive_log, [_entry("session_meta", {"id": SESSION_ID})])
    _write_jsonl(
        codex_home / "session_index.jsonl",
        [
            {
                "id": SESSION_ID,
                "thread_name": "Add Codex token tracking",
                "updated_at": "2026-05-17T18:58:27Z",
            }
        ],
    )

    index = load_session_index(codex_home)
    active_only = find_session_logs(codex_home, include_archived=False)
    with_archived = find_session_logs(codex_home, include_archived=True)

    assert index[SESSION_ID].thread_name == "Add Codex token tracking"
    assert active_only == [session_log]
    assert with_archived == [archive_log, session_log]


def _token_event(cumulative_total: int, last_total: int) -> dict[str, object]:
    return _entry(
        "event_msg",
        {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": cumulative_total - 10,
                    "cached_input_tokens": 20,
                    "output_tokens": 10,
                    "reasoning_output_tokens": 5,
                    "total_tokens": cumulative_total,
                },
                "last_token_usage": {
                    "input_tokens": last_total - 10,
                    "cached_input_tokens": 5,
                    "output_tokens": 10,
                    "reasoning_output_tokens": 5,
                    "total_tokens": last_total,
                },
                "model_context_window": 258400,
            },
        },
    )


def _entry(entry_type: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "timestamp": "2026-05-17T18:58:27.000Z",
        "type": entry_type,
        "payload": payload,
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
