# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

"""
Allineato al refactor Vision (Fase 1):
- converte il payload VisionOutput (documents/artefatti/…)
- NON usa né produce 'keywords'
- i termini per il tagging restano in semantic/tags_reviewed.yaml (Fase 2)
"""

from typing import Any, Dict, List, Optional

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

    normalized_areas: List[Dict[str, Any]] = []
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

        normalized_areas.append(entry)

    entities_raw = data.get("entities")
    entities: List[Dict[str, Any]] = []
    if isinstance(entities_raw, list):
        for ent in entities_raw:
            if not isinstance(ent, dict):
                continue
            name = str(ent.get("name", "")).strip()
            category = str(ent.get("category", "")).strip()
            if not name or not category:
                continue
            ent_payload: Dict[str, Any] = {"name": name, "category": category}
            if ent.get("description"):
                ent_payload["description"] = str(ent.get("description", "")).strip()
            examples_raw = ent.get("examples") or []
            if isinstance(examples_raw, str):
                examples_raw = [examples_raw]
            if isinstance(examples_raw, list):
                examples_norm = [str(x).strip() for x in examples_raw if str(x).strip()]
                if examples_norm:
                    ent_payload["examples"] = examples_norm
            entities.append(ent_payload)

    relations_raw = data.get("relations")
    relations: List[Dict[str, str]] = []
    if isinstance(relations_raw, list):
        for rel in relations_raw:
            if not isinstance(rel, dict):
                continue
            src = str(rel.get("from", "")).strip()
            dst = str(rel.get("to", "")).strip()
            rel_type = str(rel.get("type", "")).strip()
            if src and dst and rel_type:
                relations.append({"from": src, "to": dst, "type": rel_type})

    entity_to_area = data.get("entity_to_area")
    normalized_entity_to_area = (
        {str(k).strip(): str(v).strip() for k, v in entity_to_area.items() if str(k).strip() and str(v).strip()}
        if isinstance(entity_to_area, dict)
        else {}
    )

    entity_to_document_type = data.get("entity_to_document_type")
    normalized_entity_to_doc = (
        {
            str(k).strip(): str(v).strip()
            for k, v in entity_to_document_type.items()
            if str(k).strip() and str(v).strip()
        }
        if isinstance(entity_to_document_type, dict)
        else {}
    )

    er_model_raw = data.get("er_model")
    er_model: Dict[str, Any] = {}
    if isinstance(er_model_raw, dict):
        er_entities = er_model_raw.get("entities")
        if isinstance(er_entities, list):
            ent_list = [str(x).strip() for x in er_entities if str(x).strip()]
            if ent_list:
                er_model["entities"] = ent_list
        er_relations = er_model_raw.get("relations")
        if isinstance(er_relations, list):
            rels_out: List[Dict[str, str]] = []
            for rel in er_relations:
                if not isinstance(rel, dict):
                    continue
                src = str(rel.get("from", "")).strip()
                dst = str(rel.get("to", "")).strip()
                rel_type = str(rel.get("type", "")).strip()
                if src and dst and rel_type:
                    rels_out.append({"from": src, "to": dst, "type": rel_type})
            if rels_out:
                er_model["relations"] = rels_out

    sys = data.get("system_folders") or {}
    if not isinstance(sys, dict) or "identity" not in sys or "glossario" not in sys:
        raise ConfigError("Vision data: system_folders mancanti (identity, glossario).")

    meta = data.get("metadata_policy")
    metadata_policy = meta if isinstance(meta, dict) else None

    payload: Dict[str, Any] = {
        "version": 1,
        "source": "vision",
        "context": {"slug": slug},
        "areas": normalized_areas,
        "entities": entities,
        "relations": relations,
        "entity_to_area": normalized_entity_to_area,
        "entity_to_document_type": normalized_entity_to_doc,
        "er_model": er_model,
        "system_folders": sys,
    }
    if metadata_policy:
        payload["metadata_policy"] = metadata_policy

    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=100)


def json_to_cartelle_raw_yaml(
    data: Dict[str, Any],
    slug: str,
    raw_folders: Optional[Dict[str, List[str]]] = None,
) -> str:
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

    payload: Dict[str, Any] = {"version": 1, "source": "vision", "context": {"slug": slug}, "folders": folders}
    if isinstance(raw_folders, dict):
        payload["raw_folders"] = raw_folders
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=100)
