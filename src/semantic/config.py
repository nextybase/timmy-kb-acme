# src/semantic/config.py
"""
Loader della configurazione semantica cliente-specifica.

Scopo
-----
Restituire un oggetto `SemanticConfig` che unisce: 
1) Valori di default robusti (fallback hardcoded)
2) Override generali del cliente (output/.../config/config.yaml -> semantic_defaults)
3) Parametri locali per il tagging (output/.../semantic/semantic_mapping.yaml -> semantic_tagger)
4) Eventuali `overrides` passati a runtime (massima precedenza)

Ordine di precedenza (alto -> basso)
------------------------------------
overrides  >  semantic_mapping.yaml:semantic_tagger  >  config.yaml:semantic_defaults  >  defaults hardcoded

N.B. Modulo "puro": nessun I/O interattivo, nessun sys.exit(), nessun logger richiesto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Set

try:
    import yaml  # PyYAML è già usato nel repo
except Exception:  # pragma: no cover
    yaml = None  # degradiamo: se manca, useremo solo i default e gli overrides


__all__ = ["SemanticConfig", "load_semantic_config"]


# ----------------------------- Defaults hardcoded ----------------------------- #

_DEFAULTS = {
    "lang": "it",          # it|en|auto
    "max_pages": 5,        # numero di pagine lette per PDF
    "top_k": 10,           # massimo numero di tag proposti per documento
    "score_min": 0.40,     # soglia minima di confidenza
    "ner": True,           # Named Entity Recognition
    "keyphrases": True,    # estrazione keyphrase
    "embeddings": False,   # fase 2 (clustering sinonimi)
    "stop_tags": ["bozza", "varie"],  # blacklist locale
}

# Chiavi accettate nella sezione semantic_tagger / semantic_defaults
_ALLOWED_KEYS: Set[str] = set(_DEFAULTS.keys())


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
    stop_tags: Set[str] = field(default_factory=set)

    # Riferimenti utili per l'orchestrazione
    base_dir: Path = Path(".")               # output/timmy-kb-<slug> (resolve in load)
    semantic_dir: Path = Path("semantic")    # base_dir / "semantic" (resolve in load)
    raw_dir: Path = Path("raw")              # base_dir / "raw" (resolve in load)

    # Mapping completo (cliente-specifico) caricato da semantic_mapping.yaml
    mapping: Dict[str, Any] = field(default_factory=dict)


# ----------------------------- Helpers YAML ---------------------------------- #

def _safe_load_yaml(p: Path) -> Dict[str, Any]:
    """
    Carica YAML come dict. Se il file o PyYAML non ci sono, ritorna {}.
    Non solleva eccezioni: il chiamante ha già fallback robusti.
    """
    if not p or not p.exists() or yaml is None:
        return {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
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


def _normalize_tagger_section(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tiene solo le chiavi ammesse e forza i tipi principali.
    """
    if not d:
        return {}
    out: Dict[str, Any] = {}
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


def _merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge superficiale: b sovrascrive a.
    """
    res = dict(a or {})
    res.update(b or {})
    return res


# ----------------------------- API pubblica ---------------------------------- #

def load_semantic_config(base_dir: Path, *, overrides: Optional[Dict[str, Any]] = None) -> SemanticConfig:
    """
    Carica la configurazione semantica per il cliente sotto `base_dir`.

    Parametri:
      - base_dir: Path della sandbox cliente, es. output/timmy-kb-<slug>
      - overrides: dict opzionale con parametri espliciti (massima precedenza)

    Ritorna:
      - SemanticConfig con parametri finali e mapping completo (da semantic_mapping.yaml)
    """
    base_dir = Path(base_dir).resolve()
    semantic_dir = (base_dir / "semantic").resolve()
    raw_dir = (base_dir / "raw").resolve()

    # 1) Defaults hardcoded
    acc = dict(_DEFAULTS)

    # 2) config.yaml → semantic_defaults
    config_yaml = (base_dir / "config" / "config.yaml").resolve()
    cfg_all = _safe_load_yaml(config_yaml)
    defaults_from_cfg = _normalize_tagger_section(
        (cfg_all.get("semantic_defaults") or {}) if isinstance(cfg_all, dict) else {}
    )
    acc = _merge(acc, defaults_from_cfg)

    # 3) semantic_mapping.yaml → semantic_tagger
    semantic_mapping_yaml = (semantic_dir / "semantic_mapping.yaml").resolve()
    mapping_all = _safe_load_yaml(semantic_mapping_yaml)
    tagger_from_mapping = _normalize_tagger_section(mapping_all.get("semantic_tagger") or {})
    acc = _merge(acc, tagger_from_mapping)

    # 4) overrides espliciti
    overrides_norm = _normalize_tagger_section(overrides or {})
    acc = _merge(acc, overrides_norm)

    # Normalizza stop_tags in set lowercase
    stop_tags = set(s.lower().strip() for s in (acc.get("stop_tags") or []) if str(s).strip())

    # Costruisci l’oggetto finale (percorsi risolti con .resolve())
    cfg = SemanticConfig(
        lang=acc.get("lang", _DEFAULTS["lang"]),
        max_pages=int(acc.get("max_pages", _DEFAULTS["max_pages"])),
        top_k=int(acc.get("top_k", _DEFAULTS["top_k"])),
        score_min=float(acc.get("score_min", _DEFAULTS["score_min"])),
        ner=bool(acc.get("ner", _DEFAULTS["ner"])),
        keyphrases=bool(acc.get("keyphrases", _DEFAULTS["keyphrases"])),
        embeddings=bool(acc.get("embeddings", _DEFAULTS["embeddings"])),
        stop_tags=stop_tags,
        base_dir=base_dir,
        semantic_dir=semantic_dir,
        raw_dir=raw_dir,
        mapping=mapping_all if isinstance(mapping_all, dict) else {},
    )
    return cfg
