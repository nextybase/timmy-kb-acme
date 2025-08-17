# tests/test_path_utils.py
from pathlib import Path
import logging
import pytest

from pipeline.path_utils import (
    is_safe_subpath,
    normalize_path,
    sanitize_filename,
    is_valid_slug,
    clear_slug_regex_cache,
)

def _enable_propagation(monkeypatch):
    """
    Alcuni logger del progetto hanno propagate=False (voluto).
    Per permettere a pytest caplog di catturare i record, abilitiamo
    temporaneamente propagate su 'pipeline.path_utils'.
    """
    logger = logging.getLogger("pipeline.path_utils")
    monkeypatch.setattr(logger, "propagate", True, raising=False)
    return logger

# -----------------------------
# is_safe_subpath
# -----------------------------
def test_is_safe_subpath_true_for_descendant(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    child = base / "a" / "b"
    child.mkdir(parents=True)
    assert is_safe_subpath(child, base) is True

def test_is_safe_subpath_true_for_same_dir(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    assert is_safe_subpath(base, base) is True

def test_is_safe_subpath_false_for_sibling(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    assert is_safe_subpath(sibling, base) is False

def test_is_safe_subpath_handles_resolution_errors_gracefully(monkeypatch, caplog):
    _enable_propagation(monkeypatch)

    def boom(*_args, **_kwargs):
        raise RuntimeError("resolve failed")
    # Forziamo l'errore su Path.resolve solo per questa chiamata
    monkeypatch.setattr(Path, "resolve", boom, raising=True)

    with caplog.at_level("ERROR", logger="pipeline.path_utils"):
        assert is_safe_subpath(Path("x"), Path("y")) is False
        assert any(r.name == "pipeline.path_utils" and r.levelno == logging.ERROR for r in caplog.records)

# -----------------------------
# normalize_path
# -----------------------------
def test_normalize_path_ok(tmp_path: Path):
    target = tmp_path / "x" / "y"
    target.mkdir(parents=True)
    p = normalize_path(target)
    assert p.exists() and p.is_dir()

def test_normalize_path_on_error_is_non_fatal(monkeypatch, caplog):
    _enable_propagation(monkeypatch)

    def boom(*_args, **_kwargs):
        raise RuntimeError("resolve failed")
    monkeypatch.setattr(Path, "resolve", boom, raising=True)
    with caplog.at_level("ERROR", logger="pipeline.path_utils"):
        p = normalize_path("///invalid///")
        assert isinstance(p, Path)  # non crasha: ritorna un Path
        assert any(r.name == "pipeline.path_utils" and r.levelno == logging.ERROR for r in caplog.records)

# -----------------------------
# sanitize_filename
# -----------------------------
@pytest.mark.parametrize(
    "name,expected_contains",
    [
        ('a<>"|?*.txt', "_"),   # caratteri vietati -> underscore
        (" name \n", "name"),   # trim
        ("", "file"),           # fallback non vuoto
    ],
)
def test_sanitize_filename_basic(name, expected_contains):
    out = sanitize_filename(name)
    assert expected_contains in out
    assert len(out) > 0

def test_sanitize_filename_truncates_long_names():
    long = "x" * 300
    out = sanitize_filename(long, max_length=50)
    assert len(out) == 50

# -----------------------------
# is_valid_slug (+ cache reset) — usa sempre lo slug "dummy"
# e la struttura output/timmy-kb-dummy/ della fixture dummy_kb
# -----------------------------
def test_is_valid_slug_default_regex_from_dummy_config(dummy_kb, monkeypatch):
    # CWD = output/timmy-kb-dummy/ così path_utils trova config/config.yaml del dummy
    monkeypatch.chdir(dummy_kb["base"])
    clear_slug_regex_cache()
    assert is_valid_slug("dummy") is True         # coerente col default del modulo
    assert is_valid_slug("Cliente") is False      # maiuscole non permesse
    assert is_valid_slug("bad/slug") is False     # separatori non validi

def test_is_valid_slug_with_custom_regex_overriding_dummy_config(dummy_kb, monkeypatch):
    # Scriviamo una regex custom nella config del dummy
    cfg = dummy_kb["config"] / "config.yaml"
    cfg.write_text('slug_regex: "^[a-z]{3}[0-9]{2}$"\n', encoding="utf-8")
    monkeypatch.chdir(dummy_kb["base"])
    clear_slug_regex_cache()

    assert is_valid_slug("abc12") is True
    assert is_valid_slug("ab12") is False    # non rispetta la regex custom
    assert is_valid_slug("ABC12") is False   # maiuscole escluse

def test_is_valid_slug_malformed_regex_fallback(dummy_kb, monkeypatch, caplog):
    _enable_propagation(monkeypatch)

    # Regex malformata → log errore e fallback alla regex di default
    cfg = dummy_kb["config"] / "config.yaml"
    cfg.write_text('slug_regex: "[["\n', encoding="utf-8")
    monkeypatch.chdir(dummy_kb["base"])
    clear_slug_regex_cache()

    with caplog.at_level("ERROR", logger="pipeline.path_utils"):
        assert is_valid_slug("ok-123") is True   # accettato dal fallback default
        assert is_valid_slug("BAD") is False
        assert any(r.name == "pipeline.path_utils" and r.levelno == logging.ERROR for r in caplog.records)
