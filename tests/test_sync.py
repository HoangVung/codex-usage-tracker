from __future__ import annotations

import json
import argparse
import sys
from unittest.mock import MagicMock, patch
from pathlib import Path
import pytest

from codex_usage_tracker.paths import APP_DIR
from codex_usage_tracker.sync_supabase import (
    SyncConfig,
    load_sync_config,
    query_local_events_for_sync,
    merge_remote_events,
    sync_push,
    sync_pull,
    sync_run_auto,
    record_sync_metadata,
)
from codex_usage_tracker.cli import _run_sync


def test_sync_config_load_and_save(tmp_path: Path) -> None:
    config_path = tmp_path / "sync.json"
    
    # 1. Load empty/missing config
    config = load_sync_config(config_path)
    assert not config.loaded
    assert config.supabase_url == ""
    assert config.supabase_key == ""
    assert config.workspace_id == ""
    assert config.device_id != ""
    assert config.auto_on_refresh is False
    assert config.privacy_mode == "strict"
    assert config.error is None
    
    # 2. Save config
    config.supabase_url = "https://example.supabase.co"
    config.supabase_key = "anon-key"
    config.workspace_id = "work-123"
    config.auto_on_refresh = True
    config.privacy_mode = "redacted"
    config.save()
    
    assert config_path.exists()
    
    # 3. Reload config
    config2 = load_sync_config(config_path)
    assert config2.loaded
    assert config2.supabase_url == "https://example.supabase.co"
    assert config2.supabase_key == "anon-key"
    assert config2.workspace_id == "work-123"
    assert config2.device_id == config.device_id
    assert config2.auto_on_refresh is True
    assert config2.privacy_mode == "redacted"


def test_sync_config_error_handling(tmp_path: Path) -> None:
    config_path = tmp_path / "sync.json"
    config_path.write_text("invalid json {", encoding="utf-8")
    
    config = load_sync_config(config_path)
    assert not config.loaded
    assert config.error is not None


def test_privacy_redaction_before_push(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    from codex_usage_tracker.store import connect, init_db
    
    # Create synthetic local DB with one row containing sensitive cwd & thread_name
    with connect(db_path) as conn:
        init_db(conn)
        conn.execute(
            """
            INSERT INTO usage_events (
                record_id, session_id, thread_name, event_timestamp, source_file, line_number,
                cwd, model, input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens, total_tokens,
                cumulative_input_tokens, cumulative_cached_input_tokens, cumulative_output_tokens, cumulative_reasoning_output_tokens, cumulative_total_tokens,
                uncached_input_tokens, cache_ratio, reasoning_output_ratio, context_window_percent
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?
            )
            """,
            (
                "rec-1", "sess-1", "Sensitive Thread Name", "2026-06-11T10:00:00Z", "main.py", 10,
                "C:/Users/vungh/private_project", "gpt-4o", 100, 50, 50, 0, 150,
                100, 50, 50, 0, 150,
                50, 0.5, 0.0, 0.0
            )
        )
        
    config = SyncConfig(
        supabase_url="https://example.supabase.co",
        supabase_key="key",
        device_id="my-device-123",
        workspace_id="my-workspace"
    )
    
    # Push dry-run strict
    with patch("codex_usage_tracker.sync_supabase._supabase_request") as mock_req:
        sync_push(db_path, config, privacy_mode="strict", dry_run=False)
        assert mock_req.call_count == 1
        called_payload = mock_req.call_args[1]["payload"]
        assert len(called_payload) == 1
        row = called_payload[0]
        # Strict mode: thread_name is kept, cwd must be hidden/redacted, workspace/device id set
        assert row["record_id"] == "rec-1"
        assert row["thread_name"] == "Sensitive Thread Name"
        assert "private_project" not in row["cwd"]
        assert row["device_id"] == "my-device-123"
        assert row["workspace_id"] == "my-workspace"


def test_idempotent_merge(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    from codex_usage_tracker.store import connect, init_db
    
    # Setup local DB with an unredacted local row
    with connect(db_path) as conn:
        init_db(conn)
        conn.execute(
            """
            INSERT INTO usage_events (
                record_id, session_id, thread_name, event_timestamp, source_file, line_number,
                cwd, model, input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens, total_tokens,
                cumulative_input_tokens, cumulative_cached_input_tokens, cumulative_output_tokens, cumulative_reasoning_output_tokens, cumulative_total_tokens,
                uncached_input_tokens, cache_ratio, reasoning_output_ratio, context_window_percent,
                device_id
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?
            )
            """,
            (
                "rec-1", "sess-1", "Sensitive Thread Name", "2026-06-11T10:00:00Z", "main.py", 10,
                "C:/Users/vungh/private_project", "gpt-4o", 100, 50, 50, 0, 150,
                100, 50, 50, 0, 150,
                50, 0.5, 0.0, 0.0,
                "my-device-123"
            )
        )

    # Remote returns a redacted version of our own row, plus a new row from another device
    remote_rows = [
        {
            "record_id": "rec-1",
            "session_id": "sess-1",
            "thread_name": "[Redacted Thread]",
            "event_timestamp": "2026-06-11T10:00:00Z",
            "source_file": "main.py",
            "line_number": 10,
            "cwd": "[Redacted Workspace]",
            "model": "gpt-4o",
            "input_tokens": 100,
            "cached_input_tokens": 50,
            "output_tokens": 50,
            "reasoning_output_tokens": 0,
            "total_tokens": 150,
            "cumulative_input_tokens": 100,
            "cumulative_cached_input_tokens": 50,
            "cumulative_output_tokens": 50,
            "cumulative_reasoning_output_tokens": 0,
            "cumulative_total_tokens": 150,
            "uncached_input_tokens": 50,
            "cache_ratio": 0.5,
            "reasoning_output_ratio": 0.0,
            "context_window_percent": 0.0,
            "device_id": "my-device-123",
            "workspace_id": "my-workspace"
        },
        {
            "record_id": "rec-2",
            "session_id": "sess-2",
            "thread_name": "Remote Thread",
            "event_timestamp": "2026-06-11T11:00:00Z",
            "source_file": "other.py",
            "line_number": 20,
            "cwd": "/remote/path",
            "model": "gpt-4o",
            "input_tokens": 200,
            "cached_input_tokens": 100,
            "output_tokens": 100,
            "reasoning_output_tokens": 0,
            "total_tokens": 300,
            "cumulative_input_tokens": 200,
            "cumulative_cached_input_tokens": 100,
            "cumulative_output_tokens": 100,
            "cumulative_reasoning_output_tokens": 0,
            "cumulative_total_tokens": 300,
            "uncached_input_tokens": 100,
            "cache_ratio": 0.5,
            "reasoning_output_ratio": 0.0,
            "context_window_percent": 0.0,
            "device_id": "other-device-456",
            "workspace_id": "my-workspace"
        }
    ]

    merged_count = merge_remote_events(db_path, remote_rows, "my-device-123")
    assert merged_count == 1  # only rec-2 was merged, rec-1 was skipped to keep local fidelity
    
    with connect(db_path) as conn:
        rows = conn.execute("SELECT record_id, thread_name, device_id FROM usage_events ORDER BY record_id").fetchall()
        assert len(rows) == 2
        # rec-1 should remain unredacted
        assert rows[0]["record_id"] == "rec-1"
        assert rows[0]["thread_name"] == "Sensitive Thread Name"
        assert rows[0]["device_id"] == "my-device-123"
        # rec-2 should be successfully imported
        assert rows[1]["record_id"] == "rec-2"
        assert rows[1]["thread_name"] == "Remote Thread"
        assert rows[1]["device_id"] == "other-device-456"


@patch("codex_usage_tracker.sync_supabase._supabase_request")
def test_cli_sync_commands(mock_req: MagicMock, tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    config_path = tmp_path / "sync.json"
    
    # Mock CLI arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=db_path)
    
    # 1. Test status before init
    with patch("codex_usage_tracker.sync_supabase.DEFAULT_SYNC_PATH", config_path):
        args = argparse.Namespace(
            command="sync",
            sync_command="status",
            db=db_path,
        )
        with patch("builtins.print") as mock_print:
            code = _run_sync(args)
            assert code == 0
            mock_print.assert_any_call("Status: Not initialized")
            
    # 2. Test init
    with patch("codex_usage_tracker.sync_supabase.DEFAULT_SYNC_PATH", config_path):
        args = argparse.Namespace(
            command="sync",
            sync_command="init",
            db=db_path,
            url="https://example.supabase.co",
            key="some-key",
            workspace_id="work-abc",
            device_id="dev-xyz",
            auto="true",
            privacy="strict",
            force=True,
        )
        code = _run_sync(args)
        assert code == 0
        assert config_path.exists()
        
    # 3. Test status after init
    with patch("codex_usage_tracker.sync_supabase.DEFAULT_SYNC_PATH", config_path):
        args = argparse.Namespace(
            command="sync",
            sync_command="status",
            db=db_path,
        )
        with patch("builtins.print") as mock_print:
            code = _run_sync(args)
            assert code == 0
            mock_print.assert_any_call("Supabase URL: https://example.supabase.co")
            mock_print.assert_any_call("Workspace ID: work-abc")
            for call in mock_print.call_args_list:
                for arg in call[0]:
                    assert "some-key" not in str(arg)
            
    # 4. Test push
    # Insert a dummy row first to allow pushing
    from codex_usage_tracker.store import connect, init_db
    with connect(db_path) as conn:
        init_db(conn)
        conn.execute(
            """
            INSERT INTO usage_events (
                record_id, session_id, thread_name, event_timestamp, source_file, line_number,
                input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens, total_tokens,
                cumulative_input_tokens, cumulative_cached_input_tokens, cumulative_output_tokens, cumulative_reasoning_output_tokens, cumulative_total_tokens,
                uncached_input_tokens, cache_ratio, reasoning_output_ratio, context_window_percent
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?
            )
            """,
            (
                "rec-1", "sess-1", "Thread 1", "2026-06-11T10:00:00Z", "main.py", 10,
                100, 50, 50, 0, 150,
                100, 50, 50, 0, 150,
                50, 0.5, 0.0, 0.0
            )
        )
        
    mock_req.return_value = []
    with patch("codex_usage_tracker.sync_supabase.DEFAULT_SYNC_PATH", config_path):
        args = argparse.Namespace(
            command="sync",
            sync_command="push",
            db=db_path,
            privacy_mode=None,
            since=None,
            limit=None,
            dry_run=False,
        )
        code = _run_sync(args)
        assert code == 0
        assert mock_req.call_count == 1
        
    # 5. Test pull
    # Mock return rows for pull
    mock_req.reset_mock()
    mock_req.return_value = [
        {
            "record_id": "rec-remote",
            "session_id": "sess-2",
            "thread_name": "Remote Thread",
            "event_timestamp": "2026-06-11T10:30:00Z",
            "source_file": "main.py",
            "line_number": 10,
            "input_tokens": 100,
            "cached_input_tokens": 50,
            "output_tokens": 50,
            "reasoning_output_tokens": 0,
            "total_tokens": 150,
            "cumulative_input_tokens": 100,
            "cumulative_cached_input_tokens": 50,
            "cumulative_output_tokens": 50,
            "cumulative_reasoning_output_tokens": 0,
            "cumulative_total_tokens": 150,
            "uncached_input_tokens": 50,
            "cache_ratio": 0.5,
            "reasoning_output_ratio": 0.0,
            "context_window_percent": 0.0,
            "device_id": "remote-dev",
            "workspace_id": "work-abc"
        }
    ]
    with patch("codex_usage_tracker.sync_supabase.DEFAULT_SYNC_PATH", config_path):
        args = argparse.Namespace(
            command="sync",
            sync_command="pull",
            db=db_path,
            since=None,
            limit=None,
            dry_run=False,
        )
        code = _run_sync(args)
        assert code == 0
        assert mock_req.call_count == 1
        
    # Verify the pulled row got inserted
    with connect(db_path) as conn:
        rows = conn.execute("SELECT record_id FROM usage_events ORDER BY record_id").fetchall()
        assert len(rows) == 2
        assert rows[0]["record_id"] == "rec-1"
        assert rows[1]["record_id"] == "rec-remote"


def test_sync_privacy_mode_normal_warning(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    from codex_usage_tracker.store import connect, init_db
    with connect(db_path) as conn:
        init_db(conn)
        conn.execute(
            """
            INSERT INTO usage_events (
                record_id, session_id, event_timestamp, source_file, line_number,
                input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens, total_tokens,
                cumulative_input_tokens, cumulative_cached_input_tokens, cumulative_output_tokens, cumulative_reasoning_output_tokens, cumulative_total_tokens,
                uncached_input_tokens, cache_ratio, reasoning_output_ratio, context_window_percent
            ) VALUES (?, ?, ?, ?, ?, 10, 0, 10, 0, 20, 10, 0, 10, 0, 20, 10, 0, 0, 0)
            """,
            ("rec-warning", "sess-1", "2026-06-11T10:00:00Z", "main.py", 10)
        )
    config = SyncConfig(
        supabase_url="https://example.supabase.co",
        supabase_key="key",
        device_id="my-device-123",
        workspace_id="my-workspace"
    )
    with patch("codex_usage_tracker.sync_supabase._supabase_request") as mock_req:
        with patch("sys.stderr") as mock_stderr:
            sync_push(db_path, config, privacy_mode="normal")
            assert mock_req.call_count == 1
            # Verify warning was written to stderr
            mock_stderr.write.assert_any_call("[WARNING] normal privacy mode is selected for online sync. Local source paths, CWDs, and thread names will be uploaded without redaction.")


def test_sync_failure_does_not_break_refresh(tmp_path: Path) -> None:
    from codex_usage_tracker.store import refresh_usage_index
    # Create empty codex_home and config
    codex_home = tmp_path / "codex"
    (codex_home / "sessions").mkdir(parents=True)
    (codex_home / "session_index.jsonl").write_text("", encoding="utf-8")
    db_path = tmp_path / "usage.sqlite3"
    config_path = tmp_path / "sync.json"
    
    # Configure auto-sync
    config = SyncConfig(
        path=config_path,
        supabase_url="https://example.supabase.co",
        supabase_key="key",
        auto_on_refresh=True
    )
    config.save()
    
    # Mock sync to fail with exception
    with patch("codex_usage_tracker.sync_supabase._supabase_request", side_effect=RuntimeError("Supabase connection failed")):
        with patch("codex_usage_tracker.sync_supabase.DEFAULT_SYNC_PATH", config_path):
            result = refresh_usage_index(codex_home=codex_home, db_path=db_path, sync=True)
            # The refresh index must succeed even if the sync operation failed
            assert result.parsed_events == 0
