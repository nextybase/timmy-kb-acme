from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Iterator

import pytest
import yaml

pytest.importorskip("playwright.sync_api", reason="Playwright non disponibile: installa playwright per i test e2e.")
from playwright.sync_api import sync_playwright  # noqa: E402

PORT = 8501
E2E_MARKER = pytest.mark.e2e


def _wait_for_port(host: str, port: int, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            try:
                sock.connect((host, port))
                return
            except OSError:
                time.sleep(1)
    raise RuntimeError(f"Server Streamlit non raggiungibile su {host}:{port} entro {timeout}s")


@pytest.fixture(scope="session")
def e2e_environment(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Dict[str, Path]]:
    repo_root = Path(__file__).resolve().parents[2]
    sandbox = tmp_path_factory.mktemp("e2e_repo")
    slug = "acme-demo"

    clients_dir = sandbox / "clients_db"
    clients_dir.mkdir(parents=True, exist_ok=True)
    clients_file = clients_dir / "clients.yaml"
    clients_file.write_text(
        yaml.safe_dump([{"slug": slug, "nome": "Acme Demo", "stato": "nuovo"}], allow_unicode=True),
        encoding="utf-8",
    )

    workspace = sandbox / "output" / f"timmy-kb-{slug}"
    (workspace / "raw").mkdir(parents=True, exist_ok=True)
    (workspace / "semantic").mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "REPO_ROOT_DIR": str(sandbox),
            "CLIENTS_DB_PATH": "clients_db/clients.yaml",
            "TAGS_MODE": "stub",
            "PREVIEW_MODE": "stub",
            "PREVIEW_LOG_DIR": str(sandbox / "preview_logs"),
            "STREAMLIT_SERVER_HEADLESS": "true",
        }
    )

    log_path = sandbox / "streamlit.log"
    log_handle = log_path.open("w", encoding="utf-8")
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(repo_root / "onboarding_ui.py"),
        "--server.headless=true",
        f"--server.port={PORT}",
        "--server.fileWatcherType=none",
    ]
    proc = subprocess.Popen(cmd, cwd=repo_root, env=env, stdout=log_handle, stderr=log_handle)
    try:
        _wait_for_port("127.0.0.1", PORT, timeout=40)
    except Exception:
        proc.terminate()
        proc.wait(timeout=5)
        log_handle.close()
        raise

    yield {
        "slug": slug,
        "sandbox": sandbox,
        "log_path": log_path,
    }

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log_handle.close()


def _wait_for_db_state(db_path: Path, slug: str, expected_state: str, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = yaml.safe_load(db_path.read_text(encoding="utf-8")) or []
        for entry in data:
            if (entry or {}).get("slug") == slug and (entry or {}).get("stato") == expected_state:
                return
        time.sleep(0.5)
    raise AssertionError(f"Stato '{expected_state}' non raggiunto in {db_path}")


def _wait_for_log_line(log_path: Path, expected: str, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if log_path.exists():
            content = log_path.read_text(encoding="utf-8")
            if expected in content:
                return
        time.sleep(0.5)
    raise AssertionError(f"Log '{expected}' non trovato in {log_path}")


@E2E_MARKER
def test_enable_and_preview(e2e_environment: Dict[str, Path]) -> None:
    slug = e2e_environment["slug"]
    sandbox = e2e_environment["sandbox"]
    base_url = f"http://127.0.0.1:{PORT}"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        page.goto(f"{base_url}/?tab=manage&slug={slug}", wait_until="networkidle")
        page.get_by_role("button", name="Abilita").click()

        clients_db = sandbox / "clients_db" / "clients.yaml"
        _wait_for_db_state(clients_db, slug, "arricchito", timeout=10.0)

        page.goto(f"{base_url}/?tab=preview&slug={slug}", wait_until="networkidle")
        page.get_by_role("button", name="Avvia preview").click()

        preview_log = sandbox / "preview_logs" / f"{slug}.log"
        _wait_for_log_line(preview_log, "PREVIEW_STUB_START", timeout=10.0)

        browser.close()
