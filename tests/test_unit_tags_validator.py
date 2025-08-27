import pytest
from src.tag_onboarding import _validate_tags_reviewed

def test_validate_ok_minimal():
    data = {
        "version": "1.0",
        "reviewed_at": "2025-08-27",
        "keep_only_listed": False,
        "tags": [
            {"name": "AI", "action": "keep", "synonyms": ["artificial intelligence"]},
            {"name": "legacy", "action": "drop"},
            {"name": "ml", "action": "merge_into:AI"}
        ],
    }
    res = _validate_tags_reviewed(data)
    assert res["errors"] == []
    assert res["count"] == 3

def test_validate_missing_keys():
    res = _validate_tags_reviewed({})
    # Deve segnalare i 4 campi obbligatori
    assert any("version" in e for e in res["errors"])
    assert any("reviewed_at" in e for e in res["errors"])
    assert any("keep_only_listed" in e for e in res["errors"])
    assert any("tags" in e for e in res["errors"])

def test_validate_duplicates_and_illegal_chars():
    data = {
        "version": "1.0",
        "reviewed_at": "2025-08-27",
        "keep_only_listed": True,
        "tags": [
            {"name": "Finance", "action": "keep"},
            {"name": "finance", "action": "keep"},                 # duplicato case-insensitive
            {"name": "bad/name", "action": "drop"},                # caratteri non permessi
            {"name": "merge-no-target", "action": "merge_into:"},  # merge senza target
        ],
    }
    res = _validate_tags_reviewed(data)
    errs = "\n".join(res["errors"])
    assert "duplicato" in errs.lower()
    assert "caratteri non permessi" in errs.lower()
    assert "merge_into senza target" in errs.lower()
