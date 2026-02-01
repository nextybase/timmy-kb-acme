from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Optional

from pipeline.file_utils import safe_write_bytes
from pipeline.path_utils import to_kebab_soft


_VISION_STATEMENT_SOURCE = Path(__file__).resolve().parents[2] / "config" / "VisionStatement.pdf"


# NOTE: deterministic PDF usable by raw_ingest without extra deps.
_MINIMAL_RAW_PDF = base64.b64decode(
    b"JVBERi0xLjQKJeLjz9MKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIgPj4KZW5kb2JqCjIgMCBvYmoKPDwgL1R5cGUgL1BhZ2VzIC9LaWRzIFszIDAgUl0gL0NvdW50IDEgPj4KZW5kb2JqCjMgMCBvYmoKPDwgL1R5cGUgL1BhZ2UgL1BhcmVudCAyIDAgUiAvTWVkaWFCb3ggWzAgMCA2MTIgNzkyXSAvQ29udGVudHMgNCAwIFIgL1Jlc291cmNlcyA8PCAvRm9udCA8PCAvRjEgNSAwIFIgPj4gPj4gPj4KZW5kb2JqCjQgMCBvYmoKPDwgL0xlbmd0aCA0NCA+PgpzdHJlYW0KQlQKL0YxIDI0IFRmCjEwMCA3MDAgVGQKKEQgdW1teSBzYW1wbGUgUERGKQpUagpFVAplbmRzdHJlYW0KZW5kb2JqCjUgMCBvYmoKPDwgL1R5cGUgL0ZvbnQgL1N1YnR5cGUgL1R5cGUxIC9CYXNlRm9udCAvSGVsdmV0aWNhID4+CmVuZG9iagp4cmVmCjAgNgowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwMTUgMDAwMDAgbiAKMDAwMDAwMDA2NyAwMDAwMCBuIAowMDAwMDAwMTI2IDAwMDAwIG4gCjAwMDAwMDAyNzkgMDAwMDAgbiAKMDAwMDAwMDQwNyAwMDAwMCBuIAp0cmFpbGVyCjw8IC9TaXplIDYgL1Jvb3QgMSAwIFIgPj4Kc3RhcnR4cmVmCjUwMQolJUVPRgo="  # pragma: allowlist secret deterministic placeholder PDF stub
)  # pragma: allowlist secret deterministic placeholder PDF stub


def _load_vision_pdf_bytes() -> bytes:
    if not _VISION_STATEMENT_SOURCE.exists():
        raise RuntimeError(f"VisionStatement.pdf mancante nel repo: {_VISION_STATEMENT_SOURCE}")
    try:
        data = _VISION_STATEMENT_SOURCE.read_bytes()
    except Exception as exc:
        raise RuntimeError("VisionStatement.pdf non leggibile.") from exc
    if not data:
        raise RuntimeError("VisionStatement.pdf esistente ma vuoto.")
    return data


def ensure_raw_pdfs(base_dir: Path, *, categories: Optional[dict[str, dict[str, Any]]] = None) -> None:
    """
    Deposit a VisionStatement.pdf in every folder under raw/.

    Args:
        base_dir: workspace root.
        categories: optional category mapping used to seed additional directories.
    """
    pdf_bytes = _load_vision_pdf_bytes()
    raw_dir = base_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    candidate_dirs: set[Path] = {raw_dir}
    for child in raw_dir.iterdir():
        if child.is_dir():
            candidate_dirs.add(child)

    for category_key in (categories or {}).keys():
        candidate_dirs.add(raw_dir / to_kebab_soft(category_key))

    for subdir in sorted(candidate_dirs):
        subdir.mkdir(parents=True, exist_ok=True)
        existing_pdf = next((p for p in subdir.iterdir() if p.suffix.lower() == ".pdf"), None)
        target = existing_pdf or (subdir / "VisionStatement.pdf")
        safe_write_bytes(target, pdf_bytes, atomic=True)


def _unsupported(name: str) -> None:
    raise RuntimeError(f"{name} non disponibile nel dummy deterministico; usa la pipeline reale.")


def ensure_book_skeleton(base_dir: Path) -> None:
    _unsupported("ensure_book_skeleton")


def ensure_local_readmes(base_dir: Path, categories: Optional[dict[str, dict[str, Any]]] = None) -> list[str]:
    _unsupported("ensure_local_readmes")


def ensure_minimal_tags_db(base_dir: Path, categories: Optional[dict[str, dict[str, Any]]], *, logger: Any) -> None:  # type: ignore[override]
    _unsupported("ensure_minimal_tags_db")


def load_mapping_categories(base_dir: Path) -> dict[str, dict[str, Any]]:
    _unsupported("load_mapping_categories")


def write_basic_semantic_yaml(base_dir: Path, *, slug: str, client_name: str) -> dict[str, Any]:
    _unsupported("write_basic_semantic_yaml")


__all__ = [
    "ensure_raw_pdfs",
    "ensure_book_skeleton",
    "ensure_local_readmes",
    "ensure_minimal_tags_db",
    "load_mapping_categories",
    "write_basic_semantic_yaml",
]
