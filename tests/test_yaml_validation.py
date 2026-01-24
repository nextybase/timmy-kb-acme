# SPDX-License-Identifier: GPL-3.0-only
import pytest

from semantic.tags_validator import validate_tags_reviewed

pytestmark = pytest.mark.unit


def make_base_tag(**overrides):
    base = {
        "name": "ai",
        "action": "keep",
        "synonyms": [],
    }
    base.update(overrides)
    return base


def make_base_payload(tags):
    return {
        "version": "1.0",
        "reviewed_at": "2025-09-17",
        "keep_only_listed": False,
        "tags": tags,
    }


def _has_message(errors: list[str], message: str) -> bool:
    return any(message in err for err in errors)


def test_accepts_note():
    payload = make_base_payload([make_base_tag(note="Annotazione")])
    res = validate_tags_reviewed(payload)
    assert res["errors"] == []


def test_rejects_notes_key():
    payload = make_base_payload([make_base_tag(notes="legacy field")])
    res = validate_tags_reviewed(payload)
    assert _has_message(res["errors"], "Chiave non supportata: 'notes'. Usa 'note'.")


def test_rejects_both_keys():
    payload = make_base_payload([make_base_tag(note="ok", notes="legacy")])
    res = validate_tags_reviewed(payload)
    assert _has_message(res["errors"], "Chiave non supportata: 'notes'. Usa 'note'.")


def test_rejects_wrong_type_for_note():
    payload = make_base_payload([make_base_tag(note=["array"])])
    res = validate_tags_reviewed(payload)
    assert _has_message(res["errors"], "'note' deve essere una stringa.")
