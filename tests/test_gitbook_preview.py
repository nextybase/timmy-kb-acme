# tests/test_gitbook_preview.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import pytest

from pipeline.exceptions import PreviewError

# Import diretto della funzione (se manca, si skippa l'intero file)
try:
    from pipeline.gitbook_preview import run_gitbook_docker_preview  # type: ignore
except Exception:
    run_gitbook_docker_preview = None  # type: ignore


# --- Mini contesto compatibile con gitbook_preview.run_gitbook_docker_preview ---
@dataclass
class _MiniContext:
    slug: str
    base_dir: Path
    md_dir: Path  # <- richiesto dalla tua implementazione


def _mk_ctx(dummy_kb) -> _MiniContext:
    base = dummy_kb["base"]
    md = dummy_kb["book"]  # usiamo la cartella book/ come md_dir per l'anteprima
    return _MiniContext(slug="dummy", base_dir=base, md_dir=md)


# --- Finti risultati per subprocess.run ---
class _OK:
    returncode = 0
    stdout = "ok"
    stderr = ""


class _FAIL:
    returncode = 1
    stdout = ""
    stderr = "boom"


@pytest.mark.skipif(run_gitbook_docker_preview is None, reason="run_gitbook_docker_preview non esposto")
def test_preview_happy_path_runs_commands(dummy_kb, monkeypatch):
    ctx = _mk_ctx(dummy_kb)
    calls = []

    def fake_run(cmd, *args, **kwargs):
        # Tracciamo le chiamate senza eseguire nulla
        assert isinstance(cmd, (list, tuple)), "Il comando dovrebbe essere list/tuple"
        calls.append((tuple(cmd), kwargs))
        return _OK()

    monkeypatch.setattr(subprocess, "run", fake_run, raising=True)

    run_gitbook_docker_preview(ctx, wait_on_exit=False)

    # Deve aver invocato almeno build o serve
    assert len(calls) >= 1
    # I comandi attesi passano per docker
    joined = " ".join(" ".join(map(str, c[0])) for c in calls)
    assert "docker " in joined


@pytest.mark.skipif(run_gitbook_docker_preview is None, reason="run_gitbook_docker_preview non esposto")
def test_preview_raises_on_subprocess_failure(dummy_kb, monkeypatch):
    ctx = _mk_ctx(dummy_kb)

    def fake_run_fail(cmd, *args, **kwargs):
        # Se la funzione usa check=True (come nel build/serve), solleva CalledProcessError
        if kwargs.get("check"):
            raise subprocess.CalledProcessError(returncode=1, cmd=cmd)
        return _FAIL()

    monkeypatch.setattr(subprocess, "run", fake_run_fail, raising=True)

    with pytest.raises(PreviewError):
        run_gitbook_docker_preview(ctx, wait_on_exit=False)


@pytest.mark.skipif(run_gitbook_docker_preview is None, reason="run_gitbook_docker_preview non esposto")
def test_preview_accepts_wait_on_exit_flag(dummy_kb, monkeypatch):
    ctx = _mk_ctx(dummy_kb)
    seen = {"called": 0}

    def fake_run(cmd, *args, **kwargs):
        seen["called"] += 1
        return _OK()

    monkeypatch.setattr(subprocess, "run", fake_run, raising=True)

    # Caso detached
    run_gitbook_docker_preview(ctx, wait_on_exit=False)
    assert seen["called"] >= 1

    # Caso foreground (con cleanup finale)
    run_gitbook_docker_preview(ctx, wait_on_exit=True)
    assert seen["called"] >= 2


@pytest.mark.skipif(run_gitbook_docker_preview is None, reason="run_gitbook_docker_preview non esposto")
def test_preview_fails_on_unsafe_md_dir(dummy_kb):
    # Crea un contesto con md_dir fuori da base_dir per violare is_safe_subpath
    base = dummy_kb["base"]
    unsafe_md = base.parent / "evil-md"  # fuori da base_dir
    ctx = _MiniContext(slug="dummy", base_dir=base, md_dir=unsafe_md)

    with pytest.raises(PreviewError):
        run_gitbook_docker_preview(ctx, wait_on_exit=False)
