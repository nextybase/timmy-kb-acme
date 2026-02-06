from __future__ import annotations

# SPDX-License-Identifier: GPL-3.0-or-later
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

from tests._helpers.workspace_paths import local_workspace_dir

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_TEMP_DIR = REPO_ROOT / "test-temp"
CLIENTS_TEMP_DIR = TEST_TEMP_DIR / "clients_db"
CLIENTS_DB_TEST_DIR = CLIENTS_TEMP_DIR / ".pytest_clients_db"
OUTPUT_TEMP_DIR = TEST_TEMP_DIR / "output"
PYTEST_TEMP_DIR = TEST_TEMP_DIR / "pytest"
OBSERVABILITY_COMPOSE = REPO_ROOT / "observability" / "docker-compose.yaml"
DOCKER_BIN = shutil.which("docker")
SRC_ROOT = REPO_ROOT / "src"
import sqlite3

DUMMY_SLUG = os.getenv("CODEX_DUMMY_SLUG", "dummy-test")

from pipeline.env_constants import WORKSPACE_ROOT_ENV
from pipeline.file_utils import safe_write_text

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

    arch_files = {
        "test_architecture_paths.py",
        "test_imports.py",
        "test_preflight_import_safety.py",
    }
    contract_files = {
        "test_chunk_record_contract.py",
    }
    tools_files = {
        "test_gen_dummy_kb_import_safety.py",
        "test_tools_check.py",
    }
    for item in items:
        nodeid = getattr(item, "nodeid", "") or ""
        nodeid_norm = nodeid.replace("\\", "/")
        fspath = getattr(item, "fspath", None)
        filename = Path(str(fspath)).name if fspath is not None else ""

        if nodeid_norm.startswith("tests/architecture/") or nodeid_norm.startswith("tests/encoding/"):
            item.add_marker(pytest.mark.arch)
        elif filename in arch_files or filename.startswith("test_architecture_"):
            item.add_marker(pytest.mark.arch)

        if (
            nodeid_norm.startswith("tests/contract/")
            or filename.startswith("test_contract_")
            or filename in contract_files
        ):
            item.add_marker(pytest.mark.contract)

        if nodeid_norm.startswith("tests/ui/") or filename.startswith("test_ui_"):
            item.add_marker(pytest.mark.ui)

        if nodeid_norm.startswith("tests/semantic/") or filename.startswith("test_semantic_"):
            item.add_marker(pytest.mark.semantic)

        if nodeid_norm.startswith("tests/pipeline/") or filename.startswith("test_pipeline_"):
            item.add_marker(pytest.mark.pipeline)

        if nodeid_norm.startswith("tests/ai/") or filename.startswith("test_ai_"):
            item.add_marker(pytest.mark.ai)

        if nodeid_norm.startswith("tests/retriever/") or filename.startswith("test_retriever_"):
            item.add_marker(pytest.mark.retriever)

        if nodeid_norm.startswith("tests/scripts/"):
            item.add_marker(pytest.mark.scripts)

        if nodeid_norm.startswith("tests/tools/") or filename.startswith("test_tools_") or filename in tools_files:
            item.add_marker(pytest.mark.tools)

        if nodeid_norm.startswith("tests/e2e/"):
            item.add_marker(pytest.mark.e2e)


@pytest.fixture(autouse=True)
def _reset_semantic_api_functions() -> None:
    """Resetta le funzioni pubbliche della semantic API tra i test per evitare leak di monkeypatch."""
    from semantic import api as sapi

    _convert_service.convert_markdown = _ORIG_CONVERT_MARKDOWN
    sapi.require_reviewed_vocab = _ORIG_REQUIRE_REVIEWED_VOCAB
    sapi._require_reviewed_vocab = _ORIG_PRIVATE_REQUIRE_REVIEWED_VOCAB  # type: ignore[attr-defined]
    _frontmatter_service.enrich_frontmatter = _ORIG_ENRICH_FRONTMATTER
    _frontmatter_service.write_summary_and_readme = _ORIG_WRITE_SUMMARY_AND_README
    yield


def _require_yaml() -> None:
    """Fail-fast se PyYAML non e' disponibile nel test harness."""
    try:
        import yaml  # type: ignore # noqa: F401
    except Exception:
        pytest.fail("infrastruttura non conforme / stack incompleto: PyYAML richiesto")


_require_yaml()


def _clear_directory(base: Path) -> None:
    if not base.exists():
        return
    for child in base.iterdir():
        try:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        except OSError:
            # best-effort cleanup; ignore redundant files
            continue


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_temp_dir() -> None:
    if TEST_TEMP_DIR.exists():
        _clear_directory(TEST_TEMP_DIR)
    else:
        TEST_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    CLIENTS_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    CLIENTS_DB_TEST_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    PYTEST_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PYTEST_TMPDIR", str(PYTEST_TEMP_DIR))
    yield


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


@pytest.fixture(scope="session", autouse=True)
def _isolate_clients_db(tmp_path_factory: pytest.TempPathFactory) -> None:
    """
    Reindirizza il registry clienti e lo stato UI in una directory temporanea
    per evitare scritture nel repository durante pytest.
    """
    base_root = tmp_path_factory.mktemp("pytest_repo_root")
    (base_root / ".git").mkdir(parents=True, exist_ok=True)
    clients_db_dir = Path(os.environ.get("CLIENTS_DB_DIR", str(CLIENTS_DB_TEST_DIR)))
    clients_db_dir.mkdir(parents=True, exist_ok=True)
    ui_state_path = clients_db_dir / "ui_state.json"
    if not ui_state_path.exists():
        safe_write_text(ui_state_path, "{}\n", encoding="utf-8")

    os.environ.setdefault("REPO_ROOT_DIR", str(base_root))
    os.environ["CLIENTS_DB_DIR"] = str(clients_db_dir)
    os.environ.setdefault("CLIENTS_DB_FILE", "clients.yaml")
    os.environ.setdefault(WORKSPACE_ROOT_ENV, str(base_root))


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
    env_flag = os.getenv("TEST_OBSERVABILITY")
    enabled = env_flag not in {None, "", "0", "false", "False"}
    if not enabled:
        logger.info(
            "osservability.stack.skipped",
            extra={"reason": "TEST_OBSERVABILITY not enabled"},
        )
        yield
        return
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
        logger.info("osservability.down.scheduled", extra={"delay_s": 5.0})


# Import diretto dello script: repo root deve essere nel PYTHONPATH quando lanci pytest
@pytest.fixture(scope="session")
def sandbox_workspace(tmp_path_factory):
    """
    Workspace minimale per test unit: evita il costo di gen_dummy_kb.
    Usato solo per l'ambiente stabile (cwd + clients_db).
    """
    base_parent = tmp_path_factory.mktemp("kb-sandbox")
    base = local_workspace_dir(base_parent, DUMMY_SLUG)
    base.mkdir(parents=True, exist_ok=True)

    clients_db_file = base / "clients_db" / "clients.yaml"
    if not clients_db_file.exists():
        safe_write_text(clients_db_file, "clients: []\n")

    cfg = base / "config" / "config.yaml"
    if not cfg.exists():
        safe_write_text(cfg, "ai:\n  vision:\n    vision_statement_pdf: config/VisionStatement.pdf\n")

    return {
        "base": base,
        "config": cfg,
        "clients_db_file": clients_db_file,
        "clients_db_dir": clients_db_file.parent,
        "slug": DUMMY_SLUG,
    }



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
def _redirect_dummy_output_root(monkeypatch):
    if "TIMMY_KB_DUMMY_OUTPUT_ROOT" not in os.environ:
        monkeypatch.setenv("TIMMY_KB_DUMMY_OUTPUT_ROOT", str(TEST_TEMP_DIR))
    yield


@pytest.fixture(autouse=True)
def _stable_env(monkeypatch, sandbox_workspace):
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
    # Evita che REPO_ROOT_DIR da .env alteri i test che richiedono la repo root.
    monkeypatch.delenv("REPO_ROOT_DIR", raising=False)
    # Beta strict is enforced only when explicitly requested by the test.
    monkeypatch.setenv("TIMMY_BETA_STRICT", "0")

    # Evita side-effect su output/ del repo: se qualche codice usa default,
    # meglio che punti alla base temporanea del dummy.
    monkeypatch.chdir(sandbox_workspace["base"])

    # Reindirizza il registry clienti verso la copia temporanea
    repo_root_override = Path(sandbox_workspace["base"])
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
