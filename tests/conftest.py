from __future__ import annotations

# SPDX-License-Identifier: GPL-3.0-only
# tests/conftest.py
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
OBSERVABILITY_COMPOSE = REPO_ROOT / "observability" / "docker-compose.yaml"
DOCKER_BIN = shutil.which("docker")
SRC_ROOT = REPO_ROOT / "src"

import sqlite3

try:
    import pipeline  # type: ignore # noqa: F401
except Exception as exc:  # pragma: no cover - fail fast on misconfigured env
    raise RuntimeError("Esegui pytest con PYTHONPATH=src per importare pipeline/*") from exc

from semantic import api as _semantic_api
from semantic import convert_service as _convert_service
from semantic import frontmatter_service as _frontmatter_service

_ORIG_CONVERT_MARKDOWN = _convert_service.convert_markdown
_ORIG_REQUIRE_REVIEWED_VOCAB = _semantic_api.require_reviewed_vocab
_ORIG_PRIVATE_REQUIRE_REVIEWED_VOCAB = _semantic_api._require_reviewed_vocab  # type: ignore[attr-defined]
_ORIG_ENRICH_FRONTMATTER = _frontmatter_service.enrich_frontmatter
_ORIG_WRITE_SUMMARY_AND_README = _frontmatter_service.write_summary_and_readme


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """
    Beta 1.0: nessun supporto per runtime Streamlit headless/stub.

    Skip mirato (deterministico) solo per test UI che, nel repository corrente,
    dipendono esplicitamente da stub/headless helpers.
    Rif: docs/policies/guida_codex.md (sezione "UI testing stance (Beta 1.0)").
    """
    marker = pytest.mark.skip(reason="Test UI basato su Streamlit stub/headless: non supportato in Beta 1.0.")
    stub_ui_test_files: set[str] = {
        "test_admin_oauth.py",
        "test_config_editor_sections.py",
        "test_diff_view_sections.py",
        "test_drive_download.py",
        "test_landing_slug_sections.py",
        "test_logs_panel.py",
        "test_manage_cleanup_component.py",
        "test_manage_drive.py",
        "test_manage_modal_save.py",
        "test_manage_probe_raw.py",
        "test_manage_tags_regression.py",
        "test_new_client_config.py",
        "test_new_client_flow.py",
        "test_onboarding_ui_preflight.py",
        "test_pages_diagnostics.py",
        "test_pages_import.py",
        "test_pages_prototimmy_chat.py",
        "test_preview_stub.py",
        "test_stubs_singleton.py",
        "test_tools_check_sections.py",
        "test_workspace_helpers.py",
    }
    for item in items:
        nodeid = getattr(item, "nodeid", "") or ""
        if not (nodeid.startswith("tests/ui/") or nodeid.startswith("tests\\ui\\")):
            continue
        fspath = getattr(item, "fspath", None)
        filename = Path(str(fspath)).name if fspath is not None else ""
        if filename in stub_ui_test_files:
            item.add_marker(marker)


@pytest.fixture(autouse=True)
def _reset_semantic_api_functions() -> None:
    """Resetta le funzioni pubbliche della semantic API tra i test per evitare leak di monkeypatch."""
    from semantic import api as sapi

    sapi.convert_markdown = _ORIG_CONVERT_MARKDOWN
    sapi.require_reviewed_vocab = _ORIG_REQUIRE_REVIEWED_VOCAB
    sapi._require_reviewed_vocab = _ORIG_PRIVATE_REQUIRE_REVIEWED_VOCAB  # type: ignore[attr-defined]
    sapi.enrich_frontmatter = _ORIG_ENRICH_FRONTMATTER
    sapi.write_summary_and_readme = _ORIG_WRITE_SUMMARY_AND_README
    yield


def _require_yaml() -> None:
    """Fail-fast se PyYAML non e' disponibile nel test harness."""
    try:
        import yaml  # type: ignore # noqa: F401
    except Exception:
        pytest.fail("infrastruttura non conforme / stack incompleto: PyYAML richiesto")


_require_yaml()


def _safe_flush(fn: Any) -> None:
    try:
        fn()
    except (OSError, ValueError):
        return


def _apply_safe_stdio_flush() -> list[tuple[Any, Any]]:
    saved: list[tuple[Any, Any]] = []

    def _patch(stream: Any) -> None:
        if stream is None:
            return
        try:
            current = stream.flush
        except Exception:
            return
        if getattr(current, "_safe_flush_wrapped", False):
            return

        def _wrapped_flush() -> None:
            _safe_flush(current)

        _wrapped_flush._safe_flush_wrapped = True  # type: ignore[attr-defined]
        _wrapped_flush._safe_flush_original = current  # type: ignore[attr-defined]
        try:
            stream.flush = _wrapped_flush  # type: ignore[assignment]
        except Exception:
            return
        saved.append((stream, current))

    _patch(getattr(sys, "stdout", None))
    _patch(getattr(sys, "stderr", None))
    _patch(getattr(sys, "__stdout__", None))
    _patch(getattr(sys, "__stderr__", None))
    return saved


@pytest.fixture(scope="session", autouse=True)
def _safe_stdio_flush():
    """Rende best-effort il flush di stdout/stderr durante pytest su Windows."""
    if os.name != "nt":
        yield
        return
    saved = _apply_safe_stdio_flush()
    yield
    for stream, original in saved:
        try:
            stream.flush = original  # type: ignore[assignment]
        except Exception:
            pass


def pytest_runtest_setup(item):  # type: ignore[no-untyped-def]
    if os.name != "nt":
        return
    _apply_safe_stdio_flush()


from pipeline.file_utils import safe_write_text

# Reindirizza di default il registry clienti verso una copia interna usata solo dai test
_DEFAULT_TEST_CLIENTS_DB_DIR = Path("clients_db") / ".pytest_clients_db"
_DEFAULT_TEST_CLIENTS_DB_FILE = _DEFAULT_TEST_CLIENTS_DB_DIR / "clients.yaml"
(REPO_ROOT / _DEFAULT_TEST_CLIENTS_DB_DIR).mkdir(parents=True, exist_ok=True)
_DEFAULT_TEST_UI_STATE = _DEFAULT_TEST_CLIENTS_DB_DIR / "ui_state.json"
_DEFAULT_TEST_UI_STATE_FULL = REPO_ROOT / _DEFAULT_TEST_UI_STATE
if not _DEFAULT_TEST_UI_STATE_FULL.exists():
    safe_write_text(_DEFAULT_TEST_UI_STATE_FULL, "{}\n", encoding="utf-8")
if "CLIENTS_DB_DIR" not in os.environ:
    os.environ["CLIENTS_DB_DIR"] = str(_DEFAULT_TEST_CLIENTS_DB_DIR)
if "CLIENTS_DB_FILE" not in os.environ:
    os.environ["CLIENTS_DB_FILE"] = _DEFAULT_TEST_CLIENTS_DB_FILE.name


# Helpers per avviare lo stack osservabilità (docker compose ...)
def _compose_command(action: Sequence[str]) -> list[str]:
    assert DOCKER_BIN is not None  # guard dell'uso: verifichiamo prima di chiamare
    return [DOCKER_BIN, "compose", "-f", str(OBSERVABILITY_COMPOSE), *action]


def _run_compose_command(action: Sequence[str], *, logger: logging.Logger, check: bool = True) -> bool:
    try:
        cmd = _compose_command(action)
    except AssertionError:
        logger.warning("docker non disponibile per lo stack osservabilità", extra={"action": action})
        return False

    try:
        subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            check=check,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        logger.warning("docker non trovato durante l'esecuzione dello stack osservabilità", extra={"cmd": cmd})
        return False
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"").decode("utf-8", "ignore").strip()
        logger.warning(
            "docker compose fallito",
            extra={"cmd": cmd, "stderr": stderr},
        )
        return False
    return True


def _wait_for_port(host: str, port: int, timeout: float = 60.0) -> bool:
    stop = time.monotonic() + timeout
    while time.monotonic() < stop:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _delayed_down(delay: float, *, logger: logging.Logger) -> None:
    time.sleep(delay)
    _run_compose_command(("down",), logger=logger, check=False)


@pytest.fixture(scope="session", autouse=True)
def observability_stack_fixture():
    logger = logging.getLogger("tests.observability.stack")
    if not OBSERVABILITY_COMPOSE.exists():
        logger.debug("docker compose per osservabilità mancante; salto stack")
        yield
        return
    if DOCKER_BIN is None:
        logger.warning("docker non trovato; non avvio lo stack OTLP")
        yield
        return

    started = _run_compose_command(("up", "-d", "otel-collector"), logger=logger, check=True)
    if started:
        ready = _wait_for_port("localhost", 4318, timeout=60.0)
        if not ready:
            logger.warning(
                "porta 4318 non pronta dopo l'avvio dello stack osservabilità",
                extra={"timeout_s": 60.0},
            )
        else:
            logger.info(
                "porta_otlp_pronta",
                extra={"port": 4318, "timeout_s": 60.0},
            )
    yield
    if started:
        t = threading.Thread(target=_delayed_down, args=(5.0,), kwargs={"logger": logger}, daemon=True)
        t.start()
        t.join(timeout=15.0)
        if t.is_alive():
            logger.warning("osservability.down.timeout", extra={"timeout_s": 15.0})


# Import diretto dello script: repo root deve essere nel PYTHONPATH quando lanci pytest
try:
    from tools.gen_dummy_kb import main as _gen_dummy_main  # type: ignore
except Exception as exc:
    raise RuntimeError("tools.gen_dummy_kb non importabile per i test; verifica le dipendenze di runtime.") from exc

DUMMY_SLUG = "dummy"


def _ensure_gen_dummy_available():
    if _gen_dummy_main is None:
        pytest.fail("infrastruttura non conforme / stack incompleto: PyYAML richiesto")
    return _gen_dummy_main


def _bool_env(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v not in {"0", "false", "False", ""}


@pytest.fixture(scope="session")
def dummy_workspace(tmp_path_factory):
    """
    Crea un workspace dummy in una dir temporanea di sessione con:
      - config/config.yaml (+ VisionStatement.pdf)
      - raw/ (sempre)
      - book/ (con README.md e SUMMARY.md di default)
      - semantic/* (SOLO se DUMMY_WS_WITH_SEMANTIC=1; default: ON per retro-compatibilità test)

    Ritorna un dict con percorsi utili (anche le chiavi 'semantic_mapping' e 'cartelle_raw'
    sono sempre presenti nel dict; i file possono non esistere se DUMMY_WS_WITH_SEMANTIC=0).
    """
    base_parent = tmp_path_factory.mktemp("kbws")
    clients_db_relative = Path("clients_db/clients.yaml")

    rc = _gen_dummy_main(
        [
            "--base-dir",
            str(base_parent),
            "--slug",
            DUMMY_SLUG,
            "--records",
            "0",  # niente finanza per i test generici
            "--clients-db",
            clients_db_relative.as_posix(),
        ]
    )
    assert rc == 0, "gen_dummy_kb.py non è riuscito a creare il workspace"

    base = Path(base_parent) / f"{DUMMY_SLUG}"
    if not base.exists():  # fallback: alcuni script usano "timmy-kb-<slug>"
        base = Path(base_parent) / f"timmy-kb-{DUMMY_SLUG}"
    # normalizziamo al formato standard timmy-kb-<slug>
    if base.name != f"timmy-kb-{DUMMY_SLUG}":
        base = Path(base_parent) / f"timmy-kb-{DUMMY_SLUG}"

    cfg = base / "config" / "config.yaml"
    pdf = base / "config" / "VisionStatement.pdf"

    raw_dir = base / "raw"
    book = base / "book"

    sem_dir = base / "semantic"
    sem_map = sem_dir / "semantic_mapping.yaml"
    sem_cart = sem_dir / "cartelle_raw.yaml"

    # --- Locale minimo sempre presente ---
    cfg.parent.mkdir(parents=True, exist_ok=True)
    if not cfg.exists():
        source_cfg = REPO_ROOT / "config" / "config.yaml"
        if source_cfg.exists():
            cfg.write_text(source_cfg.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            cfg.write_text("vision_statement_pdf: config/VisionStatement.pdf\n", encoding="utf-8")

    pdf.parent.mkdir(parents=True, exist_ok=True)
    if not pdf.exists():
        source_pdf = REPO_ROOT / "config" / "VisionStatement.pdf"
        if source_pdf.exists():
            pdf.write_bytes(source_pdf.read_bytes())
        else:
            try:
                import fitz  # type: ignore

                doc = fitz.open()
                page = doc.new_page()
                page.insert_text((72, 72), "Dummy Vision")
                doc.save(str(pdf))
                doc.close()
            except Exception:
                pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")

    raw_dir.mkdir(parents=True, exist_ok=True)

    # Book con file minimi (molti test li usano)
    book.mkdir(parents=True, exist_ok=True)
    defaults = {
        "SUMMARY.md": "* [Alpha](alpha.md)\n* [Beta](beta.md)\n",
        "README.md": "# Dummy KB\n",
    }
    for name, content in defaults.items():
        target = book / name
        if not target.exists():
            target.write_text(content, encoding="utf-8")

    # --- Stub semantic opzionali (ON di default per retro-compat test) ---
    with_semantic = _bool_env("DUMMY_WS_WITH_SEMANTIC", True)
    if with_semantic:
        sem_dir.mkdir(parents=True, exist_ok=True)
        if not sem_map.exists():
            sem_map.write_text(
                "context:\n" f"  slug: {DUMMY_SLUG}\n" f"  client_name: Dummy {DUMMY_SLUG}\n",
                encoding="utf-8",
            )
        if not sem_cart.exists():
            sem_cart.write_text(
                "version: 1\n" "folders: []\n" "context:\n" f"  slug: {DUMMY_SLUG}\n",
                encoding="utf-8",
            )

    # Assert minimi sempre veri nel modello pre-Vision
    assert cfg.exists(), "config/config.yaml mancante"
    assert pdf.exists(), "config/VisionStatement.pdf mancante"
    assert raw_dir.exists(), "raw/ mancante"
    assert (book / "SUMMARY.md").exists()
    assert (book / "README.md").exists()
    # Gli assert sui semantic restano condizionati dal flag
    if with_semantic:
        assert sem_map.exists(), "semantic/semantic_mapping.yaml mancante"
        assert sem_cart.exists(), "semantic/cartelle_raw.yaml mancante"

    clients_db_dir = base / "clients_db"
    clients_db_dir.mkdir(parents=True, exist_ok=True)
    clients_db_file = clients_db_dir / "clients.yaml"

    return {
        "base": base,
        "config": cfg,
        "vision_pdf": pdf,
        "semantic_mapping": sem_map,
        "cartelle_raw": sem_cart,
        "book_dir": book,
        "raw_dir": raw_dir,
        "slug": DUMMY_SLUG,
        "client_name": f"Dummy {DUMMY_SLUG}",
        "with_semantic": with_semantic,
        "clients_db_file": clients_db_file,
        "clients_db_dir": clients_db_dir,
    }


@pytest.fixture
def dummy_ctx(dummy_workspace):
    """
    Ctx minimale compatibile con la pipeline: espone base_dir e client_name.
    Usalo per funzioni tipo provision_from_vision(..., ctx=...).
    """

    class Ctx:
        base_dir: Path = dummy_workspace["base"]
        client_name: str = dummy_workspace["client_name"]

    return Ctx()


@pytest.fixture
def dummy_logger():
    """Logger silenziato per i test: evita rumore in output."""
    log = logging.getLogger("test")
    log.setLevel(logging.INFO)
    while log.handlers:
        log.handlers.pop()
    log.addHandler(logging.NullHandler())
    return log


@pytest.fixture(autouse=True)
def _stable_env(monkeypatch, dummy_workspace):
    """
    Ambiente coerente per tutti i test:
    - evita che i test tocchino output/ reale del repo
    - lascia vuote le var assistant per forzare branch GPT quando serve
      (i test che vogliono l'assistente le settino esplicitamente)
    """
    # Harden encoding
    monkeypatch.setenv("PYTHONUTF8", "1")
    monkeypatch.setenv("PYTHONIOENCODING", "UTF-8")

    # Disabilita accidentalmente l'assistente, salvo override nel test
    monkeypatch.delenv("OBNEXT_ASSISTANT_ID", raising=False)
    monkeypatch.delenv("ASSISTANT_ID", raising=False)

    # Evita side-effect su output/ del repo: se qualche codice usa default,
    # meglio che punti alla base temporanea del dummy.
    monkeypatch.chdir(dummy_workspace["base"])

    # Reindirizza il registry clienti verso la copia temporanea
    repo_root_override = Path(dummy_workspace["base"])
    clients_db_dir = Path("clients_db")
    clients_db_file = Path("clients.yaml")
    try:
        import ui.clients_store as _clients_store

        monkeypatch.setattr(_clients_store, "REPO_ROOT", repo_root_override)
        monkeypatch.setattr(_clients_store, "DB_DIR", clients_db_dir)
        monkeypatch.setattr(_clients_store, "DB_FILE", clients_db_file)
        monkeypatch.setenv("CLIENTS_DB_DIR", clients_db_dir.as_posix())
        monkeypatch.setenv("CLIENTS_DB_FILE", clients_db_file.as_posix())
    except Exception:
        pass
    try:
        from ui.utils.stubs import reset_streamlit_stub

        reset_streamlit_stub()
    except Exception:
        pass
    yield


def build_vocab_db(base: Path, tags: Iterable[dict[str, Any]]) -> Path:
    """
    Crea semantic/tags.db nel workspace popolando tag/tag_synonyms (old schema).
    Questo permette a `load_tags_reviewed` di ritornare i canonical attesi.
    """
    from storage.tags_store import ensure_schema_v2

    semantic_dir = base / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    db_path = semantic_dir / "tags.db"
    ensure_schema_v2(str(db_path))
    with sqlite3.connect(db_path) as conn:
        for tag in tags:
            name = str(tag.get("name") or "")
            if not name:
                continue
            action = str(tag.get("action") or "keep")
            target = name
            if action.startswith("merge_into:"):
                target = action.split(":", 1)[1].strip() or name
                action = "keep"

            synonyms_raw = tag.get("synonyms") or []
            synonyms_list = []
            if target != name:
                synonyms_list.append(name)
            if isinstance(synonyms_raw, Sequence) and not isinstance(synonyms_raw, (str, bytes)):
                synonyms_list.extend(str(alias) for alias in synonyms_raw if str(alias))
            elif isinstance(synonyms_raw, (str, bytes)) and str(synonyms_raw).strip():
                synonyms_list.append(str(synonyms_raw))

            cur = conn.execute(
                "INSERT INTO tags(name, action) VALUES(?, ?) ON CONFLICT(name) DO UPDATE SET action=excluded.action",
                (target, action),
            )
            term_id = cur.lastrowid or conn.execute("SELECT id FROM tags WHERE name=?", (target,)).fetchone()[0]
            start_pos = conn.execute(
                "SELECT COALESCE(MAX(pos) + 1, 0) FROM tag_synonyms WHERE tag_id=?",
                (term_id,),
            ).fetchone()[0]
            for offset, alias in enumerate(synonyms_list):
                pos = int(start_pos) + offset
                alias_str = str(alias)
                if not alias_str:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO tag_synonyms(tag_id, alias, pos) VALUES(?, ?, ?)",
                    (term_id, alias_str, pos),
                )
        conn.commit()
    return db_path
