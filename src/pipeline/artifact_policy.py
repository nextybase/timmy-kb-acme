# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pipeline.exceptions import ArtifactPolicyViolation, ConfigError
from pipeline.normalized_index import validate_index
from pipeline.path_utils import ensure_within
from pipeline.workspace_layout import WorkspaceLayout

_MIME_BY_EXTENSION = {
    ".csv": "text/csv",
    ".db": "application/x-sqlite3",
    ".json": "application/json",
    ".md": "text/markdown",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
}


@dataclass(frozen=True)
class _CoreArtifactSpec:
    name: str
    path: Path
    extensions: tuple[str, ...]
    mime_types: tuple[str, ...]


@dataclass(frozen=True)
class _ArtifactViolation:
    name: str
    path: Path
    reason: str


def _mime_for_extension(extension: str) -> str | None:
    return _MIME_BY_EXTENSION.get(extension)


def _normalized_exts(extensions: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({ext.lower() for ext in extensions if ext}))


def _expected_specs_for_phase(
    phase: str,
    layout: WorkspaceLayout,
    *,
    stub_expected: bool,
) -> list[_CoreArtifactSpec]:
    phase_key = phase.strip().lower()
    common = [
        _CoreArtifactSpec(
            "ledger.db",
            layout.config_path.parent / "ledger.db",
            extensions=(".db",),
            mime_types=("application/x-sqlite3",),
        )
    ]
    if phase_key == "pre_onboarding":
        return [
            _CoreArtifactSpec(
                "config.yaml",
                layout.config_path,
                extensions=(".yaml", ".yml"),
                mime_types=("text/yaml",),
            ),
            _CoreArtifactSpec(
                "book/README.md",
                layout.book_dir / "README.md",
                extensions=(".md",),
                mime_types=("text/markdown",),
            ),
            _CoreArtifactSpec(
                "book/SUMMARY.md",
                layout.book_dir / "SUMMARY.md",
                extensions=(".md",),
                mime_types=("text/markdown",),
            ),
            *common,
        ]
    if phase_key == "raw_ingest":
        return [
            _CoreArtifactSpec(
                "normalized/INDEX.json",
                layout.normalized_dir / "INDEX.json",
                extensions=(".json",),
                mime_types=("application/json",),
            ),
            *common,
        ]
    if phase_key == "tag_onboarding":
        specs = [
            _CoreArtifactSpec(
                "semantic/tags_raw.csv",
                layout.semantic_dir / "tags_raw.csv",
                extensions=(".csv",),
                mime_types=("text/csv",),
            ),
            *common,
        ]
        if stub_expected:
            specs.insert(
                1,
                _CoreArtifactSpec(
                    "semantic/tags_reviewed.yaml",
                    layout.semantic_dir / "tags_reviewed.yaml",
                    extensions=(".yaml", ".yml"),
                    mime_types=("text/yaml",),
                ),
            )
        return specs
    if phase_key == "semantic_onboarding":
        return [
            _CoreArtifactSpec(
                "book/README.md",
                layout.book_dir / "README.md",
                extensions=(".md",),
                mime_types=("text/markdown",),
            ),
            _CoreArtifactSpec(
                "book/SUMMARY.md",
                layout.book_dir / "SUMMARY.md",
                extensions=(".md",),
                mime_types=("text/markdown",),
            ),
            *common,
        ]
    raise ConfigError(f"Phase non riconosciuta per artifact policy: {phase}")


def _verify_spec(layout: WorkspaceLayout, spec: _CoreArtifactSpec) -> list[_ArtifactViolation]:
    violations: list[_ArtifactViolation] = []
    try:
        ensure_within(layout.repo_root_dir, spec.path)
    except Exception:
        violations.append(_ArtifactViolation(spec.name, spec.path, "outside_workspace"))
        return violations
    if not spec.path.exists():
        violations.append(_ArtifactViolation(spec.name, spec.path, "missing"))
        return violations
    if not spec.path.is_file():
        violations.append(_ArtifactViolation(spec.name, spec.path, "not_a_file"))
        return violations
    ext = spec.path.suffix.lower()
    allowed_exts = _normalized_exts(spec.extensions)
    if allowed_exts and ext not in allowed_exts:
        violations.append(_ArtifactViolation(spec.name, spec.path, "wrong_extension"))
        return violations
    actual_mime = _mime_for_extension(ext)
    allowed_mimes = _normalized_exts(spec.mime_types)
    if allowed_mimes and (actual_mime is None or actual_mime not in allowed_mimes):
        violations.append(_ArtifactViolation(spec.name, spec.path, "wrong_mimetype"))
    return violations


def _verify_content_markdown(layout: WorkspaceLayout) -> list[_ArtifactViolation]:
    try:
        from semantic.embedding_service import list_content_markdown
    except Exception as exc:  # pragma: no cover
        return [_ArtifactViolation("book/content", layout.book_dir, f"import_failed:{type(exc).__name__}")]
    content_files = list_content_markdown(layout.book_dir)
    if content_files:
        return []
    placeholder = layout.book_dir / "<content>.md"
    return [_ArtifactViolation("book/content", placeholder, "missing")]


def _verify_raw_index(layout: WorkspaceLayout) -> list[_ArtifactViolation]:
    index_path = layout.normalized_dir / "INDEX.json"
    try:
        validate_index(
            repo_root_dir=layout.repo_root_dir,
            normalized_dir=layout.normalized_dir,
            index_path=index_path,
        )
    except ConfigError as exc:
        target = exc.file_path if isinstance(exc.file_path, Path) else index_path
        return [_ArtifactViolation("normalized/INDEX.json", Path(target), "index_invalid")]
    return []


def _build_violation_refs(layout: WorkspaceLayout, violations: Iterable[_ArtifactViolation]) -> list[str]:
    refs: list[str] = ["artifact_policy:violation"]
    for violation in violations:
        try:
            rel = violation.path.relative_to(layout.repo_root_dir).as_posix()
        except Exception:
            # Low-entropy invariant: never leak absolute paths or env-specific strings.
            rel = violation.name
        refs.append(f"artifact:{rel}:{violation.reason}")
    return refs


def enforce_core_artifacts(
    phase: str,
    *,
    layout: WorkspaceLayout,
    stub_expected: bool = False,
) -> None:
    violations: list[_ArtifactViolation] = []
    for spec in _expected_specs_for_phase(phase, layout, stub_expected=stub_expected):
        violations.extend(_verify_spec(layout, spec))
    if phase.strip().lower() == "raw_ingest":
        violations.extend(_verify_raw_index(layout))
    if phase.strip().lower() == "semantic_onboarding":
        violations.extend(_verify_content_markdown(layout))
    if violations:
        refs = _build_violation_refs(layout, violations)
        raise ArtifactPolicyViolation(
            f"Artifact policy violation ({phase}).",
            slug=layout.slug,
            file_path=violations[0].path,
            evidence_refs=refs,
        )


__all__ = ["enforce_core_artifacts"]
