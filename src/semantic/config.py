# SPDX-License-Identifier: GPL-3.0-or-later
# src/semantic/config.py
"""Loader della configurazione semantica cliente-specifica.

Scopo
-----
Restituire un oggetto `SemanticConfig` che unisce:
1) Valori di default hardcoded
2) Override generali del cliente (config.yaml -> semantic_defaults)
3) Eventuali `overrides` passati a runtime (massima precedenza)

Ordine di precedenza (alto -> basso)
------------------------------------
overrides>config.yaml:semantic_defaults>defaults hardcoded

N.B. Modulo "puro": nessun I/O interattivo, nessun sys.exit(), nessun logger richiesto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, cast

from pipeline.config_utils import load_client_settings
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.settings import Settings as PipelineSettings
from pipeline.workspace_layout import WorkspaceLayout
from pipeline.yaml_utils import yaml_read

try:  # import condizionale per UI/CLI
    from pipeline.context import ClientContext
except Exception:  # pragma: no cover
    ClientContext = None

_logger = get_structured_logger("semantic.config")

yaml: Any | None
try:
    import yaml  # PyYAML è già usato nel repo
except Exception:  # pragma: no cover
    yaml = None  # degrado: usa solo default/overrides


__all__ = ["SemanticConfig", "load_semantic_config"]


# ----------------------------- Defaults hardcoded ----------------------------- #

_DEFAULTS: dict[str, Any] = {
    "lang": "it",  # it|en|auto
    "max_pages": 5,  # numero di pagine lette per PDF
    "top_k": 10,  # massimo numero di tag proposti per documento
    "score_min": 0.40,  # soglia minima di confidenza
    "ner": True,  # Named Entity Recognition
    "keyphrases": True,  # estrazione keyphrase
    "embeddings": False,  # fase 2 (clustering sinonimi)
    "stop_tags": ["bozza", "varie"],  # blacklist locale
    "nlp_backend": "spacy",  # default SpaCy, heuristic di default se assente
    "spacy_model": "it_core_news_sm",
}

# Chiavi accettate nella sezione semantic_defaults e negli overrides runtime
_ALLOWED_KEYS: set[str] = set(_DEFAULTS.keys())


@dataclass(frozen=True)
class SemanticConfig:
    # Parametri operativi
    lang: str = "it"
    max_pages: int = 5
    top_k: int = 10
    score_min: float = 0.40
    ner: bool = True
    keyphrases: bool = True
    embeddings: bool = False
    stop_tags: set[str] = field(default_factory=set)
    nlp_backend: str = "heuristic"
    spacy_model: str = "it_core_news_sm"

    # Riferimenti utili per l'orchestrazione
    repo_root_dir: Path = Path(".")  # workspace root (resolve in load)
    semantic_dir: Path = Path("semantic")  # repo_root_dir / "semantic" (resolve in load)
    raw_dir: Path = Path("raw")  # repo_root_dir / "raw" (resolve in load)
    slug: str | None = None

    # Mapping completo (cliente-specifico) caricato da semantic_mapping.yaml
    mapping: dict[str, Any] = field(default_factory=dict)


# ----------------------------- Helpers YAML ---------------------------------- #


def _safe_load_yaml(p: Path) -> dict[str, Any]:
    """Carica YAML come dict in modo strict per semantic_mapping.yaml."""
    if yaml is None:
        raise ConfigError("PyYAML non disponibile per semantic_mapping.yaml.", file_path=str(p))
    if not p.exists():
        raise ConfigError("semantic_mapping.yaml non trovato.", file_path=str(p))
    try:
        data = yaml_read(p.parent, p)
    except Exception as exc:
        raise ConfigError("Errore lettura semantic_mapping.yaml.", file_path=str(p)) from exc
    if not isinstance(data, dict):
        raise ConfigError("semantic_mapping.yaml deve essere un mapping YAML.", file_path=str(p))
    return data


def _coerce_bool(x: Any, default: bool) -> bool:
    if isinstance(x, bool):
        return x
    if isinstance(x, str):
        val = x.strip().lower()
        if val in {"true", "1", "yes", "y", "on"}:
            return True
        if val in {"false", "0", "no", "n", "off"}:
            return False
    return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_str(value: Any, default: str) -> str:
    if isinstance(value, str):
        candidate = value.strip()
        return candidate or default
    return default


def _coerce_stop_tags(value: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(value, (list, set, tuple)):
        for item in value:
            candidate = str(item).strip().lower()
            if candidate:
                result.add(candidate)
    return result


def _normalize_tagger_section(d: dict[str, Any]) -> dict[str, Any]:
    """Tiene solo le chiavi ammesse e forza i tipi principali."""
    if not d:
        return {}
    out: dict[str, Any] = {}
    for k, v in d.items():
        if k not in _ALLOWED_KEYS:
            continue
        if k in {"max_pages", "top_k"}:
            try:
                out[k] = int(v)
            except Exception as exc:
                _logger.debug(
                    "semantic.config.coerce_int_failed",
                    extra={"key": k, "value": str(v), "reason": str(exc)},
                )
        elif k == "score_min":
            try:
                out[k] = float(v)
            except Exception as exc:
                _logger.debug(
                    "semantic.config.coerce_float_failed",
                    extra={"key": k, "value": str(v), "reason": str(exc)},
                )
        elif k in {"ner", "keyphrases", "embeddings"}:
            out[k] = _coerce_bool(v, _DEFAULTS[k])
        elif k == "stop_tags":
            # accetta lista/insieme; normalizza lowercase/stripping
            if isinstance(v, (list, set, tuple)):
                out[k] = [str(s).strip().lower() for s in v if str(s).strip()]
        elif k == "lang":
            out[k] = str(v).strip().lower()
        else:
            out[k] = v
    return out


def _merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """
    Merge superficiale: b sovrascrive a.
    """
    res = dict(a or {})
    res.update(b or {})
    return res


# ----------------------------- API pubblica ---------------------------------- #
def _resolve_layout(context_or_root: Path | Any, *, slug: str | None = None) -> WorkspaceLayout:
    if ClientContext is not None and isinstance(context_or_root, ClientContext):
        return WorkspaceLayout.from_context(context_or_root)
    repo_root_attr = getattr(context_or_root, "repo_root_dir", None)
    slug_attr = getattr(context_or_root, "slug", None)
    slug_value = slug or slug_attr
    if repo_root_attr and slug_value:
        return WorkspaceLayout.from_workspace(Path(repo_root_attr).resolve(), slug=slug_value)
    if slug is None:
        raise ConfigError(
            "Slug richiesto per risolvere il layout dal workspace root.",
            file_path=str(context_or_root),
        )
    return WorkspaceLayout.from_workspace(Path(context_or_root).resolve(), slug=slug)


def _load_client_settings(context_or_root: Path | Any, *, slug: str | None = None) -> dict[str, Any]:
    """Carica config.yaml del cliente tramite loader centralizzato (SSoT)."""
    layout = _resolve_layout(context_or_root, slug=slug)
    if ClientContext is not None and isinstance(context_or_root, ClientContext):
        try:
            settings = load_client_settings(context_or_root)
            return cast(dict[str, Any], settings.as_dict())
        except ConfigError:
            raise
        except Exception as exc:
            config_path = getattr(context_or_root, "config_path", None)
            if config_path:
                file_path = str(config_path)
            else:
                file_path = str(layout.config_path)
            raise ConfigError("Errore lettura config.yaml.", file_path=file_path) from exc

    try:
        settings = PipelineSettings.load(layout.repo_root_dir, config_path=layout.config_path)
        return cast(dict[str, Any], settings.as_dict())
    except ConfigError:
        raise
    except Exception as exc:
        raise ConfigError("Errore lettura config.yaml.", file_path=str(layout.config_path)) from exc


def load_semantic_config(
    context_or_root: Path | Any,
    *,
    overrides: Optional[dict[str, Any]] = None,
    slug: str | None = None,
) -> SemanticConfig:
    """Carica la configurazione semantica per il cliente sotto la workspace root.

    Parametri:
      - context_or_root: workspace root canonica oppure ClientContext
      - overrides: dict opzionale con parametri espliciti (massima precedenza)
      - slug: slug identificativo richiesto quando si risolve senza ClientContext

    Ritorna:
      - SemanticConfig con parametri finali e mapping completo (da semantic_mapping.yaml)
    """
    layout = _resolve_layout(context_or_root, slug=slug)
    repo_root_dir = layout.repo_root_dir
    semantic_dir = layout.semantic_dir
    raw_dir = layout.raw_dir
    config_path = layout.config_path
    resolved_slug = layout.slug

    # semantic_mapping.yaml -> strict: deve esistere e validare prima dei merge
    mapping_path = layout.mapping_path
    mapping_all = _safe_load_yaml(mapping_path)

    # 1) Defaults hardcoded
    acc: dict[str, Any] = dict(_DEFAULTS)

    # 2) config.yaml -> semantic_defaults (chiavi ammesse in _ALLOWED_KEYS)
    cfg_all = _load_client_settings(context_or_root, slug=resolved_slug)
    if (
        isinstance(cfg_all, dict)
        and "semantic_defaults" in cfg_all
        and not isinstance(cfg_all.get("semantic_defaults"), dict)
    ):
        raise ConfigError("semantic_defaults deve essere un mapping YAML.", file_path=str(config_path))
    defaults_from_cfg = _normalize_tagger_section(
        (cfg_all.get("semantic_defaults") or {}) if isinstance(cfg_all, dict) else {}
    )
    acc = _merge(acc, defaults_from_cfg)

    # 3) overrides runtime (precedenza massima)
    if overrides:
        acc = _merge(acc, _normalize_tagger_section(overrides))

    # 4) Validazione soft + coercizioni
    cfg = SemanticConfig(
        lang=_coerce_str(acc.get("lang"), _DEFAULTS["lang"]),
        max_pages=_coerce_int(acc.get("max_pages"), _DEFAULTS["max_pages"]),
        top_k=_coerce_int(acc.get("top_k"), _DEFAULTS["top_k"]),
        score_min=_coerce_float(acc.get("score_min"), _DEFAULTS["score_min"]),
        ner=_coerce_bool(acc.get("ner"), _DEFAULTS["ner"]),
        keyphrases=_coerce_bool(acc.get("keyphrases"), _DEFAULTS["keyphrases"]),
        embeddings=_coerce_bool(acc.get("embeddings"), _DEFAULTS["embeddings"]),
        stop_tags=_coerce_stop_tags(acc.get("stop_tags")),
        nlp_backend=_coerce_str(acc.get("nlp_backend"), _DEFAULTS["nlp_backend"]),
        spacy_model=_coerce_str(acc.get("spacy_model"), _DEFAULTS["spacy_model"]),
        repo_root_dir=repo_root_dir,
        semantic_dir=semantic_dir,
        raw_dir=raw_dir,
        mapping=mapping_all if isinstance(mapping_all, dict) else {},
        slug=resolved_slug,
    )
    return cfg
