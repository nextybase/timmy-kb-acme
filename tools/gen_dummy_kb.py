# SPDX-License-Identifier: GPL-3.0-or-later
"""
Shim di compatibilità per `tools.gen_dummy_kb`.

La logica vive in `src.tools.gen_dummy_kb`; qui re-esponiamo le funzioni
per mantenere invariati gli import nei test e negli script.
"""

from __future__ import annotations

import logging
from typing import Any

import src.tools.gen_dummy_kb as _impl
from src.tools.gen_dummy_kb import *  # noqa: F401,F403

# Espone i helper privati per permettere monkeypatch nei test.
_client_base = _impl._client_base
_pdf_path = _impl._pdf_path
_register_client = _impl._register_client
_run_vision_with_timeout = _impl._run_vision_with_timeout
_write_basic_semantic_yaml = _impl._write_basic_semantic_yaml
_call_drive_min = _impl._call_drive_min
_call_drive_build_from_mapping = _impl._call_drive_build_from_mapping
_call_drive_emit_readmes = _impl._call_drive_emit_readmes
_purge_previous_state = _impl._purge_previous_state
# Conserva il riferimento all'impl originale di build_payload per evitare ricorsione.
_build_payload_impl = _impl.build_payload


def _sync_shim_to_impl() -> None:
    """Propaga nel modulo reale eventuali monkeypatch applicati allo shim."""
    if _client_base is not _impl._client_base:
        _impl._client_base = _client_base  # type: ignore[assignment]
    if _pdf_path is not _impl._pdf_path:
        _impl._pdf_path = _pdf_path  # type: ignore[assignment]
    if _register_client is not _impl._register_client:
        _impl._register_client = _register_client  # type: ignore[assignment]
    if _run_vision_with_timeout is not _impl._run_vision_with_timeout:
        _impl._run_vision_with_timeout = _run_vision_with_timeout  # type: ignore[assignment]
    if _write_basic_semantic_yaml is not _impl._write_basic_semantic_yaml:
        _impl._write_basic_semantic_yaml = _write_basic_semantic_yaml  # type: ignore[assignment]
    if _call_drive_min is not _impl._call_drive_min:
        _impl._call_drive_min = _call_drive_min  # type: ignore[assignment]
    if _call_drive_build_from_mapping is not _impl._call_drive_build_from_mapping:
        _impl._call_drive_build_from_mapping = _call_drive_build_from_mapping  # type: ignore[assignment]
    if _call_drive_emit_readmes is not _impl._call_drive_emit_readmes:
        _impl._call_drive_emit_readmes = _call_drive_emit_readmes  # type: ignore[assignment]
    if _purge_previous_state is not _impl._purge_previous_state:
        _impl._purge_previous_state = _purge_previous_state  # type: ignore[assignment]
    if build_payload is not _impl.build_payload:
        _impl.build_payload = build_payload  # type: ignore[assignment]


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - delega pura
    _sync_shim_to_impl()
    _main = getattr(_impl, "main")
    return _main(argv)


def build_payload(
    *,
    slug: str,
    client_name: str,
    enable_drive: bool,
    enable_vision: bool,
    records_hint: str | None,
    logger: logging.Logger,
) -> dict[str, Any]:  # pragma: no cover - delega pura
    _sync_shim_to_impl()
    return _build_payload_impl(
        slug=slug,
        client_name=client_name,
        enable_drive=enable_drive,
        enable_vision=enable_vision,
        records_hint=records_hint,
        logger=logger,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
