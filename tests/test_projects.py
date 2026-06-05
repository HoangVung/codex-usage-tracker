from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.projects import (
    annotate_rows_with_project_identity,
    load_project_config,
    project_identity_for_cwd,
    write_project_template,
)


def test_project_identity_derives_git_metadata_with_redacted_remote(tmp_path: Path) -> None:
    repo = tmp_path / "school-automation"
    subdir = repo / "tools" / "reports"
    git_dir = repo / ".git"
    subdir.mkdir(parents=True)
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/feature/usage\n", encoding="utf-8")
    (git_dir / "config").write_text(
        '[remote "origin"]\n\turl = git@github.com:district/school-automation.git\n',
        encoding="utf-8",
    )
    config_path = tmp_path / "projects.json"
    key = project_identity_for_cwd(str(subdir))["project_key"]
    config_path.write_text(
        json.dumps(
            {
                "aliases": {key: "School Automation"},
                "tags": {"School Automation": ["teacher-tools", "reports"]},
            }
        ),
        encoding="utf-8",
    )

    identity = project_identity_for_cwd(str(subdir), load_project_config(config_path))

    assert identity["project_name"] == "School Automation"
    assert identity["project_relative_cwd"] == "tools/reports"
    assert identity["git_branch"] == "feature/usage"
    assert identity["git_remote_label"] == "school-automation"
    assert identity["git_remote_hash"] is not None
    assert "github.com" not in str(identity["git_remote_hash"])
    assert identity["project_tags"] == ["reports", "teacher-tools"]


def test_project_template_ignored_paths_and_row_annotation(tmp_path: Path) -> None:
    project_config = tmp_path / "projects.json"
    ignored = tmp_path / "ignore-me"
    ignored.mkdir()

    written = write_project_template(project_config)
    payload = json.loads(project_config.read_text(encoding="utf-8"))
    payload["ignored_paths"] = [str(ignored)]
    project_config.write_text(json.dumps(payload), encoding="utf-8")
    rows = annotate_rows_with_project_identity(
        [{"cwd": str(ignored / "nested"), "total_tokens": 10}],
        load_project_config(project_config),
    )

    assert written == project_config
    assert rows[0]["project_ignored"] is True
    assert rows[0]["project_name"] == "nested"
