# SPDX-License-Identifier: GPL-3.0-or-later
from contextlib import contextmanager

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
    assert payload["command"][0].endswith("python.exe")


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
