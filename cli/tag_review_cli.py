# SPDX-License-Identifier: GPL-3.0-only
# cli/tag_review_cli.py
"""CLI minimale per rivedere i tag in doc_entities (SpaCy/HiTL)."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import yaml

from semantic.entities_review import (
    TagReviewItem,
    fetch_docs_with_suggested_tags,
    fetch_tags_for_doc,
    update_tag_status,
)
from storage.tags_store import ensure_schema_v2 as ensure_doc_entities_table


def _load_mapping(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def cmd_list(args: argparse.Namespace) -> None:
    db_path = Path(args.db)
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_doc_entities_table(str(db_path))
        docs = fetch_docs_with_suggested_tags(conn, limit=args.limit)
    finally:
        conn.close()

    if not docs:
        print("Nessun documento con tag 'suggested' trovato.")
        return

    print(f"Documenti con tag 'suggested' (max {args.limit}):")
    for doc_uid, cnt in docs:
        print(f"- {doc_uid} ({cnt} suggerimenti)")


def _print_tag_table(items: Sequence[TagReviewItem]) -> None:
    if not items:
        print("Nessun tag trovato.")
        return
    print(f"{'#':>3}  {'AREA':<12}  {'ENTITY_ID':<20}  {'LABEL':<30}  {'CONF':>5}  {'STATUS':<10}  {'ORIGIN':<10}")
    print("-" * 100)
    for idx, item in enumerate(items, start=1):
        print(
            f"{idx:>3}  "
            f"{item.area_key:<12}  "
            f"{item.entity_id:<20}  "
            f"{item.label:<30}  "
            f"{item.confidence:>5.2f}  "
            f"{item.status:<10}  "
            f"{item.origin:<10}"
        )


def cmd_review(args: argparse.Namespace) -> None:
    db_path = Path(args.db)
    mapping_path = Path(args.mapping)
    mapping = _load_mapping(mapping_path)
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_doc_entities_table(str(db_path))
        items = fetch_tags_for_doc(
            conn,
            doc_uid=args.doc_uid,
            mapping=mapping,
            status_filter=("suggested", "approved", "rejected"),
        )
        if not items:
            print(f"Nessun tag trovato per doc_uid='{args.doc_uid}'.")
            return

        while True:
            print(f"\nTag per doc_uid='{args.doc_uid}':\n")
            _print_tag_table(items)
            choice = input(
                "\nSeleziona indice da modificare (q=esci, a=approva tutti i suggested): "
            ).strip()
            if choice.lower() == "q":
                break
            if choice.lower() == "a":
                suggested = [i for i in items if i.status == "suggested"]
                if not suggested:
                    print("Nessun tag 'suggested' da approvare.")
                    continue
                for it in suggested:
                    update_tag_status(
                        conn,
                        doc_uid=it.doc_uid,
                        area_key=it.area_key,
                        entity_id=it.entity_id,
                        new_status="approved",
                        origin=it.origin,
                    )
                conn.commit()
            else:
                if not choice.isdigit():
                    print("Input non valido.")
                    continue
                idx = int(choice)
                if not (1 <= idx <= len(items)):
                    print("Indice fuori range.")
                    continue
                item = items[idx - 1]
                print(
                    f"\nSelezionato:\n"
                    f"  area    : {item.area_key}\n"
                    f"  entity  : {item.entity_id}\n"
                    f"  label   : {item.label}\n"
                    f"  conf    : {item.confidence:.2f}\n"
                    f"  status  : {item.status}\n"
                )
                action = input("A = approve, R = reject, S = skip: ").strip().lower()
                if action not in ("a", "r", "s"):
                    print("Azione non valida.")
                    continue
                if action == "s":
                    continue
                new_status = "approved" if action == "a" else "rejected"
                update_tag_status(
                    conn,
                    doc_uid=item.doc_uid,
                    area_key=item.area_key,
                    entity_id=item.entity_id,
                    new_status=new_status,
                    origin=item.origin,
                )
                conn.commit()

            # ricarica lista aggiornata
            items = fetch_tags_for_doc(
                conn,
                doc_uid=args.doc_uid,
                mapping=mapping,
                status_filter=("suggested", "approved", "rejected"),
            )
    finally:
        conn.close()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Revisione tag semantici (doc_entities).")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="Elenca i documenti con tag 'suggested'.")
    p_list.add_argument("--db", required=True, help="Percorso a semantic/tags.db.")
    p_list.add_argument("--limit", type=int, default=50, help="Max doc mostrati.")
    p_list.set_defaults(func=cmd_list)

    p_review = sub.add_parser("review", help="Rivedi i tag per un doc_uid (interattivo).")
    p_review.add_argument("--db", required=True, help="Percorso a semantic/tags.db.")
    p_review.add_argument("--mapping", required=True, help="Percorso a semantic_mapping.yaml.")
    p_review.add_argument("--doc-uid", required=True, help="doc_uid del documento.")
    p_review.set_defaults(func=cmd_review)

    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":  # pragma: no cover
    main()
