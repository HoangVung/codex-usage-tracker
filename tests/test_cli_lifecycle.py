from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SESSION_ID = "019e374d-c19f-7da3-a44f-8de043a7a64e"


def test_setup_support_bundle_and_reset_db_cli(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = tmp_path / "pricing.json"
    allowance_path = tmp_path / "allowance.json"
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"
    marketplace_path = tmp_path / "marketplace.json"
    support_path = tmp_path / "support.json"

    setup = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "--pricing",
        str(pricing_path),
        "--allowance",
        str(allowance_path),
        "setup",
        "--codex-home",
        str(codex_home),
        "--plugin-dir",
        str(plugin_dir),
        "--marketplace",
        str(marketplace_path),
        "--skip-pricing",
    )

    assert setup.returncode == 0
    assert "Codex Usage Tracker setup summary" in setup.stdout
    assert "Restart Codex" in setup.stdout
    assert plugin_dir.exists()
    assert db_path.exists()

    support = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "--pricing",
        str(pricing_path),
        "--allowance",
        str(allowance_path),
        "support-bundle",
        "--codex-home",
        str(codex_home),
        "--output",
        str(support_path),
    )
    bundle = json.loads(support_path.read_text(encoding="utf-8"))

    assert support.returncode == 0
    assert bundle["privacy"]["contains_raw_logs"] is False
    assert bundle["refresh"]["parsed_events"] == "1"
    assert "low_cache_ratio" in bundle["thresholds"]["keys"]
    assert "SECRET RAW PROMPT" not in json.dumps(bundle)

    reset_without_confirm = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "reset-db",
    )
    reset = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "reset-db",
        "--yes",
    )

    assert reset_without_confirm.returncode == 1
    assert "Re-run with --yes" in reset_without_confirm.stderr
    assert reset.returncode == 0
    assert "Raw Codex logs were not touched" in reset.stdout


def _run_cli(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "codex_usage_tracker", *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=_subprocess_env(),
    )


def _make_codex_home(tmp_path: Path) -> Path:
    codex_home = tmp_path / ".codex"
    log_dir = codex_home / "sessions" / "2026" / "05" / "17"
    log_path = log_dir / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    _write_jsonl(
        codex_home / "session_index.jsonl",
        [
            {
                "id": SESSION_ID,
                "thread_name": "Synthetic setup test",
                "updated_at": "2026-05-17T18:58:27Z",
            }
        ],
    )
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": SESSION_ID}),
            _entry("turn_context", {"turn_id": "turn-a", "model": "gpt-5.5"}),
            _entry(
                "response_item",
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "SECRET RAW PROMPT"}],
                },
            ),
            _token_event(100, 100),
        ],
    )
    return codex_home


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


def _subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    repo_root = Path(__file__).resolve().parents[1]
    src_path = str(repo_root / "src")
    env["PYTHONPATH"] = (
        f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
        if env.get("PYTHONPATH")
        else src_path
    )
    return env
