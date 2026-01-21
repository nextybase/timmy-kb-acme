# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Iterator

import pytest
import yaml  # type: ignore

from ui.pages.registry import PagePaths, url_path_for

pytest.importorskip("playwright.sync_api", reason="Playwright non disponibile: installa playwright per i test e2e.")
from playwright.sync_api import Locator, sync_playwright  # noqa: E402

PORT = 8501
MANAGE_ROUTE = url_path_for(PagePaths.MANAGE) or "manage"
PREVIEW_ROUTE = url_path_for(PagePaths.PREVIEW) or "preview"
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
    slug = "dummy"
    (sandbox / ".git").mkdir(parents=True, exist_ok=True)

    clients_dir = sandbox / "clients_db"
    clients_dir.mkdir(parents=True, exist_ok=True)
    clients_file = clients_dir / "clients.yaml"
    clients_file.write_text(
        yaml.safe_dump([{"slug": slug, "nome": "Dummy Demo", "stato": "nuovo"}], allow_unicode=True),
        encoding="utf-8",
    )

    workspace = sandbox / "output" / f"timmy-kb-{slug}"
    raw_dir = workspace / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (workspace / "semantic").mkdir(parents=True, exist_ok=True)
    (raw_dir / "sample.pdf").write_bytes(b"%PDF-1.4\n%EOF\n")

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
        str(repo_root / "src" / "timmy_kb" / "ui" / "onboarding_ui.py"),
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
        "repo_root": repo_root,
    }

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log_handle.close()
    report_dir = repo_root / "playwright-report"
    try:
        report_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(log_path, report_dir / "streamlit.log")
    except Exception:
        pass


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
    repo_root = e2e_environment["repo_root"]
    base_url = f"http://127.0.0.1:{PORT}"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        page.goto(f"{base_url}/{MANAGE_ROUTE}?slug={slug}", wait_until="networkidle")
        page.wait_for_function("window.prerenderReady === true", timeout=20000)
        report_dir = repo_root / "playwright-report"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "manage.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(report_dir / "manage.png"), full_page=True)
        buttons_text = "\n".join(page.locator("button").all_inner_texts())
        (report_dir / "buttons_manage.txt").write_text(buttons_text, encoding="utf-8")
        use_client_button = page.locator("div[data-testid='stButton']:has-text('Usa questo cliente') button")
        if use_client_button.count():
            _click_last(use_client_button)
            page.wait_for_timeout(1000)
        page.wait_for_selector("text=Avvia arricchimento semantico", timeout=15000)
        semantic_button = page.locator("div[data-testid='stButton']:has-text('Avvia arricchimento semantico') button")
        semantic_button.first.wait_for(state="attached", timeout=15000)
        (report_dir / "counts_manage.txt").write_text(f"semantic_buttons={semantic_button.count()}\n", encoding="utf-8")
        _click_last(semantic_button)
        page.wait_for_selector("textarea", timeout=30000)
        (report_dir / "manage_modal.html").write_text(page.content(), encoding="utf-8")
        page.wait_for_selector("text=Abilita", timeout=15000)
        enable_button = page.locator("div[data-testid='stButton']:has-text('Abilita') button")
        enable_button.first.wait_for(state="attached", timeout=15000)
        _click_last(enable_button)

        clients_db = sandbox / "clients_db" / "clients.yaml"
        _wait_for_db_state(clients_db, slug, "arricchito", timeout=10.0)

        page.goto(f"{base_url}/{PREVIEW_ROUTE}?slug={slug}", wait_until="networkidle")
        preview_log = sandbox / "preview_logs" / f"{slug}.log"
        page.get_by_role("button", name="Avvia preview").click()
        _wait_for_log_line(preview_log, "PREVIEW_STUB_START", timeout=10.0)

        page.get_by_role("button", name="Arresta preview").click()
        _wait_for_log_line(preview_log, "PREVIEW_STUB_STOP", timeout=10.0)

        browser.close()


def _click_last(locator: Locator) -> None:
    handles = locator.element_handles()
    if not handles:
        return

    def _is_visible(handle: Locator.ElementHandle) -> bool:
        try:
            return bool(handle.is_visible())
        except Exception:
            try:
                return bool(
                    handle.evaluate(
                        "el => !!(el.offsetParent || el.getClientRects().length) && "
                        "getComputedStyle(el).visibility !== 'hidden' && "
                        "getComputedStyle(el).opacity !== '0'"
                    )
                )
            except Exception:
                return False

    for handle in reversed(handles):
        if not _is_visible(handle):
            continue
        try:
            handle.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass
        handle.click(force=True)
        return

    # Nessun handle visibile: fallback al click forzato sull'ultimo
    handles[-1].click(force=True)
