from __future__ import annotations

from typing import Any, Dict, List

import yaml

from pipeline.exceptions import ConfigError


def vision_to_semantic_mapping_yaml(data: Dict[str, Any], slug: str) -> str:
    """
    Converte il payload Vision v1.0-beta in semantic_mapping.yaml (1:1 con il JSON dell'assistente).
    Nessun uso di 'keywords' legacy.
    """
    if not isinstance(data, dict):
        raise ConfigError("Vision data: atteso un oggetto JSON.")
    if data.get("status") == "halt":
        raise ConfigError("Vision HALT: impossibile generare semantic_mapping.yaml senza struttura base.")

    areas = data.get("areas")
    if not isinstance(areas, list) or not (3 <= len(areas) <= 9):
        raise ConfigError("Vision data: 'areas' deve contenere tra 3 e 9 elementi.")

    payload: Dict[str, Any] = {
        "version": 1,
        "source": "vision",
        "context": {"slug": slug},
        "areas": [],
        "system_folders": {},
    }

    for idx, area in enumerate(areas):
        if not isinstance(area, dict):
            raise ConfigError(f"Vision data: area #{idx} non è un oggetto JSON.")
        entry: Dict[str, Any] = {
            "key": str(area.get("key", "")).strip(),
            "ambito": str(area.get("ambito", "")).strip(),
            "descrizione_breve": str(area.get("descrizione_breve", "")).strip(),
        }
        dd = area.get("descrizione_dettagliata") or {}
        if isinstance(dd, dict):
            entry["descrizione_dettagliata"] = {
                "include": [str(x).strip() for x in (dd.get("include") or []) if str(x).strip()],
                "exclude": [str(x).strip() for x in (dd.get("exclude") or []) if str(x).strip()],
            }
            if dd.get("artefatti_note"):
                entry["descrizione_dettagliata"]["artefatti_note"] = str(dd["artefatti_note"]).strip()
        else:
            entry["descrizione_dettagliata"] = {"include": [], "exclude": []}

        docs = area.get("documents") or []
        if isinstance(docs, str):
            docs = [docs]
        arts = area.get("artefatti") or []
        if isinstance(arts, str):
            arts = [arts]
        entry["documents"] = [str(x).strip() for x in docs if str(x).strip()]
        entry["artefatti"] = [str(x).strip() for x in arts if str(x).strip()]

        corr = area.get("correlazioni") or {}
        if isinstance(corr, dict):
            out_corr: Dict[str, Any] = {}
            if isinstance(corr.get("entities"), list):
                out_corr["entities"] = corr["entities"]
            if isinstance(corr.get("relations"), list):
                out_corr["relations"] = corr["relations"]
            if isinstance(corr.get("chunking_hints"), list):
                out_corr["chunking_hints"] = corr["chunking_hints"]
            if out_corr:
                entry["correlazioni"] = out_corr

        payload["areas"].append(entry)

    sys = data.get("system_folders") or {}
    if not isinstance(sys, dict) or "identity" not in sys or "glossario" not in sys:
        raise ConfigError("Vision data: system_folders mancanti (identity, glossario).")
    payload["system_folders"] = sys

    meta = data.get("metadata_policy")
    if isinstance(meta, dict):
        payload["metadata_policy"] = meta

    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=100)


def json_to_cartelle_raw_yaml(data: Dict[str, Any], slug: str) -> str:
    """
    Converte il payload Vision v1.0-beta in semantic/_raw_from_mapping.yaml.
    examples <- documents (fallback: descrizione_dettagliata.include)
    + system folders: identity/ e glossario/
    """
    if not isinstance(data, dict):
        raise ConfigError("Vision data: atteso un oggetto JSON.")
    if data.get("status") == "halt":
        raise ConfigError("Vision HALT: impossibile generare cartelle_raw da struttura assente.")

    areas = data.get("areas")
    if not isinstance(areas, list) or not (3 <= len(areas) <= 9):
        raise ConfigError("Vision data: 'areas' deve contenere tra 3 e 9 elementi.")

    folders: List[Dict[str, Any]] = []
    for idx, area in enumerate(areas):
        if not isinstance(area, dict):
            raise ConfigError(f"Vision data: area #{idx} non è un oggetto JSON.")
        key = area.get("key")
        ambito = area.get("ambito")
        descr_breve = area.get("descrizione_breve", "")

        docs = area.get("documents") or []
        if isinstance(docs, str):
            docs = [docs]
        include_fallback: List[str] = []
        dd = area.get("descrizione_dettagliata") or {}
        if isinstance(dd, dict):
            include_fallback = dd.get("include") or []
            if isinstance(include_fallback, str):
                include_fallback = [include_fallback]
            if not isinstance(include_fallback, list):
                include_fallback = []
        examples = [str(x).strip() for x in (docs or include_fallback) if str(x).strip()]

        folders.append(
            {
                "key": str(key),
                "title": str(ambito) if isinstance(ambito, str) and ambito.strip() else str(key),
                "description": str(descr_breve) if isinstance(descr_breve, str) else "",
                "examples": examples,
            }
        )

    sys = data.get("system_folders") or {}
    identity_docs: List[str] = []
    gloss_arts: List[str] = []
    if isinstance(sys, dict):
        ident = sys.get("identity") or {}
        if isinstance(ident, dict):
            identity_docs = ident.get("documents") or []
            if isinstance(identity_docs, str):
                identity_docs = [identity_docs]
            if not isinstance(identity_docs, list):
                identity_docs = []
        gloss = sys.get("glossario") or {}
        if isinstance(gloss, dict):
            gloss_arts = gloss.get("artefatti") or []
            if isinstance(gloss_arts, str):
                gloss_arts = [gloss_arts]
            if not isinstance(gloss_arts, list):
                gloss_arts = []

    folders.append(
        {
            "key": "identity",
            "title": "Identità",
            "description": "Documenti identificativi e titoli abilitanti",
            "examples": [str(x).strip() for x in identity_docs if str(x).strip()],
        }
    )
    folders.append(
        {
            "key": "glossario",
            "title": "Glossario",
            "description": "Termini e definizioni vincolanti (artefatti di sistema)",
            "examples": [str(x).strip() for x in gloss_arts if str(x).strip()],
        }
    )

    payload = {"version": 1, "source": "vision", "context": {"slug": slug}, "folders": folders}
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=100)
