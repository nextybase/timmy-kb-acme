# tests/test_config_utils.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
import yaml
import pytest

from pipeline.config_utils import (
    Settings,
    write_client_config_file,
    get_client_config,
    validate_preonboarding_environment,
    safe_write_file,
    update_config_with_drive_ids,
)
from pipeline.exceptions import ConfigError, PreOnboardingValidationError


# --- Helper: contesto minimale compatibile con config_utils ---
@dataclass
class _MiniContext:
    slug: str
    base_dir: Path
    output_dir: Path
    config_path: Path


def _mk_ctx(dummy_kb) -> _MiniContext:
    base = dummy_kb["base"]
    return _MiniContext(
        slug="dummy",
        base_dir=base,
        output_dir=base,
        config_path=(dummy_kb["config"] / "config.yaml"),
    )


# -----------------------------
# Settings (Pydantic)
# -----------------------------
def test_settings_ok_with_required_fields(monkeypatch):
    # Isoliamo i test dall'ENV del processo
    for k in ("DRIVE_ID", "SERVICE_ACCOUNT_FILE", "GITHUB_TOKEN", "LOG_LEVEL", "DEBUG"):
        monkeypatch.delenv(k, raising=False)

    s = Settings(
        DRIVE_ID="drive",
        SERVICE_ACCOUNT_FILE="/tmp/sa.json",
        GITHUB_TOKEN="gh_tok",
        slug="dummy",
        LOG_LEVEL="INFO",
        DEBUG=False,
    )
    assert s.DRIVE_ID == "drive"
    assert s.slug == "dummy"


def test_settings_missing_critical_raises(monkeypatch):
    # Rimuoviamo DRIVE_ID per essere certi che manchi
    monkeypatch.delenv("DRIVE_ID", raising=False)

    with pytest.raises(ValueError):
        Settings(  # manca DRIVE_ID
            SERVICE_ACCOUNT_FILE="/tmp/sa.json",
            GITHUB_TOKEN="gh_tok",
            slug="dummy",
        )


def test_settings_missing_slug_raises(monkeypatch):
    # Settiamo i critici via ENV per far fallire sullo slug mancante
    monkeypatch.setenv("DRIVE_ID", "drive-env")
    monkeypatch.setenv("SERVICE_ACCOUNT_FILE", "/tmp/sa.json")
    monkeypatch.setenv("GITHUB_TOKEN", "gh_tok")

    with pytest.raises(ValueError):
        Settings()  # slug mancante


# -----------------------------
# write_client_config_file / get_client_config
# -----------------------------
def test_write_and_get_client_config_roundtrip(dummy_kb):
    ctx = _mk_ctx(dummy_kb)
    cfg = {"cartelle_raw_yaml": ["raw/a.yaml"], "k": 1}
    path = write_client_config_file(ctx, cfg)
    assert path == ctx.config_path and path.exists()

    out = get_client_config(ctx)
    assert out["k"] == 1
    assert out["cartelle_raw_yaml"] == ["raw/a.yaml"]


def test_write_client_config_creates_backup_if_exists(dummy_kb):
    ctx = _mk_ctx(dummy_kb)

    # Prima scrittura
    write_client_config_file(ctx, {"k": 1})
    assert ctx.config_path.exists()

    # Seconda scrittura -> deve creare .bak
    write_client_config_file(ctx, {"k": 2})
    bak = ctx.config_path.with_suffix(ctx.config_path.suffix + ".bak")
    assert bak.exists()
    # Il file finale deve contenere k:2
    assert get_client_config(ctx)["k"] == 2


def test_get_client_config_missing_file_raises(dummy_kb):
    ctx = _mk_ctx(dummy_kb)
    if ctx.config_path.exists():
        ctx.config_path.unlink()
    with pytest.raises(ConfigError):
        get_client_config(ctx)


def test_get_client_config_malformed_yaml_raises(dummy_kb):
    ctx = _mk_ctx(dummy_kb)
    ctx.config_path.parent.mkdir(parents=True, exist_ok=True)
    ctx.config_path.write_text("a: [1, 2\n", encoding="utf-8")  # YAML invalido
    with pytest.raises(ConfigError):
        get_client_config(ctx)


# -----------------------------
# validate_preonboarding_environment
# -----------------------------
def test_validate_preonboarding_missing_config_raises(dummy_kb, monkeypatch):
    ctx = _mk_ctx(dummy_kb)
    if ctx.config_path.exists():
        ctx.config_path.unlink()
    with pytest.raises(PreOnboardingValidationError):
        validate_preonboarding_environment(ctx)


def test_validate_preonboarding_missing_required_keys_raises(dummy_kb):
    ctx = _mk_ctx(dummy_kb)
    write_client_config_file(ctx, {"foo": "bar"})  # manca cartelle_raw_yaml
    with pytest.raises(PreOnboardingValidationError):
        validate_preonboarding_environment(ctx)


def test_validate_preonboarding_creates_logs_and_passes(dummy_kb):
    ctx = _mk_ctx(dummy_kb)
    # config minimo valido
    write_client_config_file(ctx, {"cartelle_raw_yaml": ["raw/a.yaml"]})
    logs_dir = ctx.base_dir / "logs"
    if logs_dir.exists():
        # pulizia preventiva per testare autogenerazione
        for p in logs_dir.glob("*"):
            p.unlink()
        logs_dir.rmdir()
    validate_preonboarding_environment(ctx)
    assert logs_dir.exists() and logs_dir.is_dir()


# -----------------------------
# safe_write_file
# -----------------------------
def test_safe_write_file_atomically_writes_and_backs_up(tmp_path: Path):
    target = tmp_path / "x" / "conf.yaml"

    # Prima scrittura
    safe_write_file(target, "k: 1\n")
    assert target.exists()
    assert yaml.safe_load(target.read_text(encoding="utf-8")) == {"k": 1}

    # Seconda scrittura -> deve creare .bak e aggiornare contenuto
    safe_write_file(target, "k: 2\n")
    bak = target.with_suffix(target.suffix + ".bak")
    assert bak.exists()
    assert yaml.safe_load(target.read_text(encoding="utf-8")) == {"k": 2}


def test_safe_write_file_errors_are_wrapped(tmp_path: Path, monkeypatch):
    target = tmp_path / "x" / "conf.yaml"

    def boom(*_a, **_kw):
        raise OSError("disk full")

    # Forziamo failure durante lo swap atomico
    monkeypatch.setattr(Path, "replace", boom, raising=True)
    with pytest.raises(Exception) as ei:
        safe_write_file(target, "a: 1\n")
    # deve essere PipelineError, ma non importiamo direttamente per evitare coupling
    assert "Errore scrittura file" in str(ei.value)


# -----------------------------
# update_config_with_drive_ids
# -----------------------------
def test_update_config_with_drive_ids_updates_and_backs_up(dummy_kb):
    ctx = _mk_ctx(dummy_kb)
    # config iniziale
    write_client_config_file(ctx, {"a": 1, "b": 2})

    # aggiorniamo solo alcune chiavi
    update_config_with_drive_ids(ctx, {"a": 9})

    # finale: a==9, b resta 2
    data = yaml.safe_load(ctx.config_path.read_text(encoding="utf-8"))
    assert data["a"] == 9 and data["b"] == 2

    # deve esistere almeno un backup
    bak = ctx.config_path.with_suffix(ctx.config_path.suffix + ".bak")
    assert bak.exists()
