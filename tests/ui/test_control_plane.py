# SPDX-License-Identifier: GPL-3.0-or-later
from contextlib import contextmanager
from pathlib import Path

from ui.utils import control_plane


class DummyCompleted:
    stdout = ""
    stderr = ""
    returncode = 0


def _capture_run(monkeypatch, *, env_record):
    def fake_run(command, *, env, capture_output, text, **_):
        env_record["TIMMY_BETA_STRICT"] = env.get("TIMMY_BETA_STRICT")
        return DummyCompleted()

    monkeypatch.setattr(control_plane.subprocess, "run", fake_run)


def test_run_control_plane_tool_preserves_strict_env(monkeypatch):
    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    env_record: dict[str, str | None] = {}
    _capture_run(monkeypatch, env_record=env_record)
    payload = control_plane.run_control_plane_tool(
        tool_module="ui.utils.control_plane",
        slug="dummy",
        action="test",
    )
    assert env_record["TIMMY_BETA_STRICT"] == "1"
    assert Path(payload["command"][0]).name.lower() in {"python", "python.exe"}


def test_non_strict_step_runs_forced_context(monkeypatch):
    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    env_record: dict[str, str | None] = {}
    _capture_run(monkeypatch, env_record=env_record)
    recorded: list[tuple[str, str]] = []

    @contextmanager
    def fake_non_strict(step_name: str, *, slug: str, logger: object):
        recorded.append((step_name, slug))
        yield

    monkeypatch.setattr(control_plane, "_non_strict_step", fake_non_strict)
    control_plane.run_control_plane_tool(
        tool_module="ui.utils.control_plane",
        slug="dummy",
        action="test",
        non_strict_step="vision_enrichment",
    )
    assert recorded == [("vision_enrichment", "dummy")]
    assert env_record["TIMMY_BETA_STRICT"] == "1"


def test_run_control_plane_tool_parses_json_with_trailing_stdout_logs(monkeypatch):
    class CompletedWithLogs:
        stdout = (
            "2026-02-15 12:00:00 INFO tool.start\n"
            '{"status":"ok","mode":"control_plane","slug":"dummy","action":"test","errors":[],"warnings":[],"artifacts":[],"returncode":0,"timmy_beta_strict":"1"}\n'
            "2026-02-15 12:00:01 INFO tool.complete"
        )
        stderr = ""
        returncode = 0

    def fake_run(command, *, env, capture_output, text, **_):
        _ = command, env, capture_output, text
        return CompletedWithLogs()

    monkeypatch.setattr(control_plane.subprocess, "run", fake_run)

    result = control_plane.run_control_plane_tool(
        tool_module="ui.utils.control_plane",
        slug="dummy",
        action="test",
    )

    assert result["payload"]["status"] == "ok"
    assert result["payload"]["errors"] == []


def test_run_control_plane_tool_applies_env_overrides(monkeypatch):
    env_record: dict[str, str | None] = {}

    class CompletedNoOutput:
        stdout = ""
        stderr = ""
        returncode = 0

    def fake_run(command, *, env, capture_output, text, **_):
        _ = command, capture_output, text
        env_record["REPO_ROOT_DIR"] = env.get("REPO_ROOT_DIR")
        env_record["WORKSPACE_ROOT_DIR"] = env.get("WORKSPACE_ROOT_DIR")
        return CompletedNoOutput()

    monkeypatch.setattr(control_plane.subprocess, "run", fake_run)

    control_plane.run_control_plane_tool(
        tool_module="ui.utils.control_plane",
        slug="dummy",
        action="test",
        env_overrides={
            "REPO_ROOT_DIR": "C:/repo",
            "WORKSPACE_ROOT_DIR": "C:/repo/output/timmy-kb-dummy",
        },
    )

    assert env_record["REPO_ROOT_DIR"] == "C:/repo"
    assert env_record["WORKSPACE_ROOT_DIR"] == "C:/repo/output/timmy-kb-dummy"
