# SPDX-License-Identifier: GPL-3.0-or-later
import logging

from semantic.tags_extractor import copy_local_pdfs_to_raw


def test_copy_local_pdfs_accepts_uppercase_extension(tmp_path):
    base = tmp_path / "kb"
    src = base / "incoming"
    raw = base / "raw"
    src.mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)

    # Crea file PDF con estensione maiuscola
    (src / "DOC1.PDF").write_bytes(b"%PDF-1.4\n%dummy\n")

    logger = logging.getLogger("test.copy_upper")
    copied = copy_local_pdfs_to_raw(src, raw, logger)
    assert copied == 1
    assert (raw / "DOC1.PDF").exists()
