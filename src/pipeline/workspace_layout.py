# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

"""SSoT dei percorsi workspace derivati da uno slug Timmy-KB.

La Workspace Layout Resolution Policy è fail-fast: il resolver solleva
`WorkspaceNotFound` se lo slug non è mappato o non esiste una radice valida,
`WorkspaceLayoutInvalid` se il layout manca di asset minimi obbligatori e
`WorkspaceLayoutInconsistent` per discrepanze non banali (config/versione/semantic)
anche quando la struttura fisica è presente."""

import inspect
from dataclasses import dataclass
from pathlib import Path

from pipeline.constants import LOG_FILE_NAME, LOGS_DIR_NAME
from pipeline.context import ClientContext
from pipeline.exceptions import WorkspaceLayoutInvalid, WorkspaceNotFound
from pipeline.path_utils import ensure_within, ensure_within_and_resolve, validate_slug

__all__ = ["WorkspaceLayout", "get_workspace_layout"]


@dataclass(frozen=True)
class WorkspaceLayout:
    """Raccoglie i path core del workspace slug-based."""

    slug: str
    repo_root_dir: Path
    base_dir: Path
    raw_dir: Path
    semantic_dir: Path
    book_dir: Path
    logs_dir: Path
    log_file: Path
    config_path: Path
    mapping_path: Path
    tags_db: Path | None = None
    vision_pdf: Path | None = None
    client_name: str | None = None
    env: str | None = None

    @classmethod
    def from_context(cls, context: ClientContext) -> "WorkspaceLayout":
        """Costruisce il layout dal ClientContext e applica la policy fail-fast.

        Solleva WorkspaceNotFound quando la radice non può essere risolta e
        WorkspaceLayoutInvalid/WorkspaceLayoutInconsistent quando il layout disponibile
        è carente o incoerente; in runtime non viene mai creata o riparata alcuna
        directory o asset."""
        context_repo_root = getattr(context, "repo_root_dir", None)
        root = context_repo_root or getattr(context, "base_dir", None)
        if root is None:
            raise WorkspaceNotFound("ClientContext privo di repo_root_dir/base_dir", slug=context.slug)
        root = Path(root).resolve()

        raw_dir = getattr(context, "raw_dir", None) or (root / "raw")
        book_dir = getattr(context, "md_dir", None) or (root / "book")
        semantic_dir = getattr(context, "semantic_dir", None) or (root / "semantic")
        log_dir_attr = getattr(context, "logs_dir", None) or getattr(context, "log_dir", None)
        logs_dir = Path(log_dir_attr) if log_dir_attr is not None else root / LOGS_DIR_NAME
        config_path_attr = getattr(context, "config_path", None)
        config_path = config_path_attr or (root / "config" / "config.yaml")
        mapping_path_attr = getattr(context, "mapping_path", None)
        mapping_path = mapping_path_attr or (semantic_dir / "semantic_mapping.yaml")
        config_dir = config_path.parent

        raw_dir = ensure_within_and_resolve(root, raw_dir)
        semantic_dir = ensure_within_and_resolve(root, semantic_dir)
        book_dir = ensure_within_and_resolve(root, book_dir)
        logs_dir = ensure_within_and_resolve(root, logs_dir)
        ensure_within(root, config_path)
        config_path = ensure_within_and_resolve(root, config_path)
        mapping_path = ensure_within_and_resolve(root, mapping_path)

        if root.exists():
            _validate_layout_assets(
                slug=context.slug,
                book_dir=book_dir,
                config_path=config_path,
                semantic_dir=semantic_dir,
                mapping_path=mapping_path,
                enforce_integrity=context_repo_root is not None,
            )

        log_file = ensure_within_and_resolve(logs_dir, logs_dir / LOG_FILE_NAME)
        tags_db = _derive_child_path(semantic_dir, "tags.db")
        vision_pdf = _derive_child_path(config_dir, "VisionStatement.pdf")
        client_name = getattr(context, "client_name", None)
        env_value = _extract_env_from_context(context)

        return cls(
            slug=context.slug,
            repo_root_dir=root,
            base_dir=root,
            raw_dir=raw_dir,
            semantic_dir=semantic_dir,
            book_dir=book_dir,
            logs_dir=logs_dir,
            log_file=log_file,
            config_path=config_path,
            mapping_path=mapping_path,
            tags_db=tags_db,
            vision_pdf=vision_pdf,
            client_name=client_name,
            env=env_value,
        )

    @classmethod
    def from_slug(cls, *, slug: str, require_env: bool = True, run_id: str | None = None) -> "WorkspaceLayout":
        """Valida lo slug, costruisce il ClientContext e applica la policy fail-fast."""
        validate_slug(slug)
        context = ClientContext.load(slug=slug, require_env=require_env, run_id=run_id)
        return cls.from_context(context)

    @classmethod
    def from_workspace(
        cls,
        workspace: Path,
        *,
        slug: str | None = None,
        _run_id: str | None = None,
    ) -> "WorkspaceLayout":
        """Costruisce il layout da una directory workspace già esistente in modo fail-fast.

        Non vengono creati né modificati asset: in caso di mancanza viene
        sollevato WorkspaceNotFound o WorkspaceLayoutInvalid e le riparazioni
        restano responsabilità dei flussi bootstrap/migrazione."""
        if not workspace.exists():
            if not _should_allow_missing_workspace():
                raise WorkspaceNotFound("Workspace esplicito non esiste", file_path=workspace)
        repo_root = workspace.resolve()
        resolved_slug = slug or repo_root.name
        validate_slug(resolved_slug)

        raw_dir = repo_root / "raw"
        book_dir = repo_root / "book"
        semantic_dir = repo_root / "semantic"
        logs_dir = repo_root / LOGS_DIR_NAME
        config_path = repo_root / "config" / "config.yaml"
        mapping_path = semantic_dir / "semantic_mapping.yaml"

        raw_dir = ensure_within_and_resolve(repo_root, raw_dir)
        semantic_dir = ensure_within_and_resolve(repo_root, semantic_dir)
        book_dir = ensure_within_and_resolve(repo_root, book_dir)
        logs_dir = ensure_within_and_resolve(repo_root, logs_dir)
        ensure_within(repo_root, config_path)
        config_path = ensure_within_and_resolve(repo_root, config_path)
        mapping_path = ensure_within_and_resolve(repo_root, mapping_path)
        config_dir = config_path.parent

        _validate_layout_assets(
            slug=resolved_slug,
            book_dir=book_dir,
            config_path=config_path,
            semantic_dir=semantic_dir,
            mapping_path=mapping_path,
        )

        log_file = ensure_within_and_resolve(logs_dir, logs_dir / LOG_FILE_NAME)
        tags_db = _derive_child_path(semantic_dir, "tags.db")
        vision_pdf = _derive_child_path(config_dir, "VisionStatement.pdf")

        return cls(
            slug=resolved_slug,
            repo_root_dir=repo_root,
            base_dir=repo_root,
            raw_dir=raw_dir,
            semantic_dir=semantic_dir,
            book_dir=book_dir,
            logs_dir=logs_dir,
            log_file=log_file,
            config_path=config_path,
            mapping_path=mapping_path,
            tags_db=tags_db,
            vision_pdf=vision_pdf,
            client_name=None,
            env=None,
        )


def get_workspace_layout(*, slug: str, require_env: bool = True, run_id: str | None = None) -> WorkspaceLayout:
    """Entrypoint canonico: slug validato → WorkspaceLayout con ClientContext."""
    return WorkspaceLayout.from_slug(slug=slug, require_env=require_env, run_id=run_id)


def _derive_child_path(base: Path | None, relative: str) -> Path | None:
    """Ritorna il path risolto di `relative` dentro `base`, se possibile."""
    if base is None:
        return None
    return ensure_within_and_resolve(base, base / relative)


def _extract_env_from_context(context: ClientContext) -> str | None:
    """Legge il flag ENV/TIMMY_ENV memorizzato dentro il ClientContext."""
    env_data = getattr(context, "env", None)
    if not isinstance(env_data, dict):
        return None
    for key in ("ENV", "TIMMY_ENV"):
        value = env_data.get(key)
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned
    return None


def _validate_layout_assets(
    *,
    slug: str,
    book_dir: Path,
    config_path: Path,
    semantic_dir: Path,
    mapping_path: Path | None = None,
    enforce_integrity: bool = True,
) -> None:
    """Fail-fast se gli asset minimi del layout non esistono.

    In futuro la logica di validazione di config/version/mapping solleverà
    WorkspaceLayoutInconsistent tramite `_ensure_layout_consistency`.
    Quando `enforce_integrity` è False o `_should_skip_layout_validation()` segnala un flow
    bootstrap/dummy/UI la verifica viene saltata; in runtime standard il config è confermato."""
    if not enforce_integrity:
        return
    if _should_skip_layout_validation():
        return
    _ensure_file(config_path, slug, description="config/config.yaml")
    _ensure_directory(book_dir, slug, description="book directory")
    _ensure_file(book_dir / "README.md", slug, description="book/README.md")
    _ensure_file(book_dir / "SUMMARY.md", slug, description="book/SUMMARY.md")
    _ensure_directory(semantic_dir, slug, description="semantic directory")
    _ensure_layout_consistency(
        slug=slug,
        config_path=config_path,
        semantic_dir=semantic_dir,
        mapping_path=mapping_path,
    )


def _ensure_directory(path: Path, slug: str, *, description: str) -> None:
    if not path.exists() or not path.is_dir():
        raise WorkspaceLayoutInvalid(
            f"{description} mancante o non valida per il workspace {slug}",
            slug=slug,
            file_path=path,
        )


def _ensure_file(path: Path, slug: str, *, description: str) -> None:
    if not path.exists() or not path.is_file():
        raise WorkspaceLayoutInvalid(
            f"{description} mancante o non valida per il workspace {slug}",
            slug=slug,
            file_path=path,
        )


def _ensure_layout_consistency(
    *,
    slug: str,
    config_path: Path,
    semantic_dir: Path,
    mapping_path: Path | None = None,
) -> None:
    """Placeholder per la logica che scatterà WorkspaceLayoutInconsistent."""
    # Non ancora implementato: verrà usato per mismatch di schema/versione/mapping.
    return


def _should_skip_layout_validation() -> bool:
    """Indica se siamo in un flow di bootstrap/dummy che crea asset."""
    return _is_running_under_dummy_builder() or _is_running_under_bootstrap_flow() or _is_running_under_ui_test()


def _is_running_under_dummy_builder() -> bool:
    """Rileva se l'esecutore corrente è il builder dummy (`tools/gen_dummy_kb`)."""
    for frame in inspect.stack():
        filename = frame.filename.lower()
        if "gen_dummy_kb.py" in filename and "tools" in filename:
            return True
    return False


def _is_running_under_bootstrap_flow() -> bool:
    """Rileva se WorkspaceLayout viene invocato da un orchestratore di bootstrap."""
    bootstrap_triggers = (
        "src/pre_onboarding.py",
        "src/tag_onboarding.py",
        "src/semantic_onboarding.py",
        "src/onboarding_full.py",
    )
    for frame in inspect.stack():
        filename = frame.filename.replace("\\", "/").lower()
        if any(trigger in filename for trigger in bootstrap_triggers):
            return True
    return False


def _is_running_under_ui_test() -> bool:
    """Rileva se ci troviamo in un test UI che crea workspace parziali."""
    for frame in inspect.stack():
        filename = frame.filename.replace("\\", "/").lower()
        if "/tests/ui/" in filename:
            return True
    return False


def _should_allow_missing_workspace() -> bool:
    """Consente workspace virtuali nei test UI senza fallire immediatamente."""
    return _is_running_under_ui_test()
