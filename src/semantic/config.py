# SPDX-License-Identifier: GPL-3.0-only
# src/semantic/config.py
"""Loader della configurazione semantica cliente-specifica.

Scopo
-----
Restituire un oggetto `SemanticConfig` che unisce:
1) Valori di default robusti (fallback hardcoded)
2) Override generali del cliente (output/.../config/config.yaml -> semantic_defaults)
3) Parametri locali per il tagging (output/.../semantic/semantic_mapping.yaml -> semantic_tagger)
4) Eventuali `overrides` passati a runtime (massima precedenza)

Ordine di precedenza (alto -> basso)
------------------------------------
overrides>semantic_mapping.yaml:semantic_tagger>config.yaml:semantic_defaults>defaults hardcoded

N.B. Modulo "puro": nessun I/O interattivo, nessun sys.exit(), nessun logger richiesto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, cast

from pipeline.config_utils import load_client_settings
from pipeline.exceptions import ConfigError
from pipeline.settings import Settings as PipelineSettings
from pipeline.yaml_utils import yaml_read

try:  # compat per import in UI/CLI
    from pipeline.context import ClientContext
except Exception:  # pragma: no cover
    ClientContext = None

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
    "nlp_backend": "spacy",  # default SpaCy, fallback heuristic se assente
    "spacy_model": "it_core_news_sm",
}

# Chiavi accettate nella sezione semantic_tagger / semantic_defaults
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
    base_dir: Path = Path(".")  # output/timmy-kb-<slug> (resolve in load)
    semantic_dir: Path = Path("semantic")  # base_dir / "semantic" (resolve in load)
    raw_dir: Path = Path("raw")  # base_dir / "raw" (resolve in load)

    # Mapping completo (cliente-specifico) caricato da semantic_mapping.yaml
    mapping: dict[str, Any] = field(default_factory=dict)


# ----------------------------- Helpers YAML ---------------------------------- #


def _safe_load_yaml(p: Path) -> dict[str, Any]:
    """Carica YAML come dict.

    Se il file o PyYAML non ci sono, ritorna {}.
    Non solleva eccezioni: il chiamante ha già fallback robusti.
    """
    if not p or yaml is None:
        return {}
    try:
        if not p.exists():
            return {}
        data = yaml_read(p.parent, p) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


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
            except Exception:
                pass
        elif k == "score_min":
            try:
                out[k] = float(v)
            except Exception:
                pass
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
def _load_client_settings(base_dir: Path | Any) -> dict[str, Any]:
    """Carica config.yaml del cliente tramite loader centralizzato (SSoT)."""
    if ClientContext is not None and isinstance(base_dir, ClientContext):
        try:
            settings = load_client_settings(base_dir)
            return cast(dict[str, Any], settings.as_dict())
        except Exception:
            return {}

    base_dir = Path(base_dir).resolve()
    config_path = (base_dir / "config" / "config.yaml").resolve()
    try:
        settings = PipelineSettings.load(base_dir, config_path=config_path)
        return cast(dict[str, Any], settings.as_dict())
    except ConfigError:
        return {}
    except Exception:
        return {}


def load_semantic_config(base_dir: Path | Any, *, overrides: Optional[dict[str, Any]] = None) -> SemanticConfig:
    """Carica la configurazione semantica per il cliente sotto `base_dir`.

    Parametri:
      - base_dir: Path della sandbox cliente (es. output/timmy-kb-<slug>) oppure ClientContext
      - overrides: dict opzionale con parametri espliciti (massima precedenza)

    Ritorna:
      - SemanticConfig con parametri finali e mapping completo (da semantic_mapping.yaml)
    """
    ctx = base_dir if ClientContext is not None and isinstance(base_dir, ClientContext) else None
    base_dir_path = Path(getattr(ctx, "base_dir", None) or base_dir).resolve()
    semantic_dir = (base_dir_path / "semantic").resolve()
    raw_dir = (base_dir_path / "raw").resolve()

    # 1) Defaults hardcoded
    acc: dict[str, Any] = dict(_DEFAULTS)

    # 2) config.yaml -> semantic_defaults
    cfg_all = _load_client_settings(base_dir)
    defaults_from_cfg = _normalize_tagger_section(
        (cfg_all.get("semantic_defaults") or {}) if isinstance(cfg_all, dict) else {}
    )
    acc = _merge(acc, defaults_from_cfg)

    # 3) semantic_mapping.yaml -> semantic_tagger
    mapping_path = semantic_dir / "semantic_mapping.yaml"
    mapping_all = _safe_load_yaml(mapping_path)

    semantic_tagger_raw = mapping_all.get("semantic_tagger") if isinstance(mapping_all, dict) else {}
    semantic_tagger = _normalize_tagger_section(semantic_tagger_raw if isinstance(semantic_tagger_raw, dict) else {})

    acc = _merge(acc, semantic_tagger)

    # 4) overrides runtime (precedenza massima)
    if overrides:
        acc = _merge(acc, _normalize_tagger_section(overrides))

    # 5) Validazione soft + coercizioni
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
        base_dir=base_dir_path,
        semantic_dir=semantic_dir,
        raw_dir=raw_dir,
        mapping=mapping_all if isinstance(mapping_all, dict) else {},
    )
    return cfg
