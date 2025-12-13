# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from types import ModuleType
from typing import Any, Callable, Sequence

DEFAULT_DUMMY_PREFIXES: tuple[str, ...] = ("src.tools.dummy", "tools.dummy")


def _import_dummy_module(suffix: str, prefixes: Sequence[str]) -> ModuleType:
    tried = []
    for prefix in prefixes:
        full_name = f"{prefix}.{suffix}"
        try:
            return import_module(full_name)
        except ImportError as exc:
            tried.append(f"{full_name}: {exc}")
    raise ImportError(f"Impossibile importare {suffix} da {prefixes!r}: {', '.join(tried)}")


@dataclass(frozen=True)
class DummyHelpers:
    client_base: Callable[..., Any]
    pdf_path: Callable[..., Any]
    build_dummy_payload: Callable[..., Any]
    register_client: Callable[..., Any]
    validate_dummy_structure: Callable[..., Any]
    ensure_book_skeleton: Callable[..., Any]
    ensure_local_readmes: Callable[..., Any]
    ensure_minimal_tags_db: Callable[..., Any]
    ensure_raw_pdfs: Callable[..., Any]
    load_mapping_categories: Callable[..., Any]
    write_basic_semantic_yaml: Callable[..., Any]
    run_vision_with_timeout: Callable[..., Any]


@dataclass(frozen=True)
class DriveBindings:
    call_drive_build_from_mapping: Callable[..., Any]
    call_drive_emit_readmes: Callable[..., Any]
    call_drive_min: Callable[..., Any]


def load_dummy_helpers(prefixes: Sequence[str] | None = None) -> DummyHelpers:
    if prefixes is None:
        prefixes = DEFAULT_DUMMY_PREFIXES

    bootstrap = _import_dummy_module("bootstrap", prefixes)
    orchestrator = _import_dummy_module("orchestrator", prefixes)
    semantic = _import_dummy_module("semantic", prefixes)
    vision = _import_dummy_module("vision", prefixes)

    return DummyHelpers(
        client_base=getattr(bootstrap, "client_base"),
        pdf_path=getattr(bootstrap, "pdf_path"),
        build_dummy_payload=getattr(orchestrator, "build_dummy_payload"),
        register_client=getattr(orchestrator, "register_client"),
        validate_dummy_structure=getattr(orchestrator, "validate_dummy_structure"),
        ensure_book_skeleton=getattr(semantic, "ensure_book_skeleton"),
        ensure_local_readmes=getattr(semantic, "ensure_local_readmes"),
        ensure_minimal_tags_db=getattr(semantic, "ensure_minimal_tags_db"),
        ensure_raw_pdfs=getattr(semantic, "ensure_raw_pdfs"),
        load_mapping_categories=getattr(semantic, "load_mapping_categories"),
        write_basic_semantic_yaml=getattr(semantic, "write_basic_semantic_yaml"),
        run_vision_with_timeout=getattr(vision, "run_vision_with_timeout"),
    )


def load_dummy_drive_helpers(prefixes: Sequence[str] | None = None) -> DriveBindings:
    if prefixes is None:
        prefixes = DEFAULT_DUMMY_PREFIXES

    drive = _import_dummy_module("drive", prefixes)

    return DriveBindings(
        call_drive_build_from_mapping=getattr(drive, "call_drive_build_from_mapping"),
        call_drive_emit_readmes=getattr(drive, "call_drive_emit_readmes"),
        call_drive_min=getattr(drive, "call_drive_min"),
    )
