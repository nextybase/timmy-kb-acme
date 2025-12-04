# SPDX-License-Identifier: GPL-3.0-only
from inspect import signature

from pipeline import file_utils as be_file_utils
from pipeline import path_utils as be_path_utils
from ui.utils import core as ui_core


def test_safe_write_text_signature_matches_backend() -> None:
    assert signature(ui_core.safe_write_text) == signature(be_file_utils.safe_write_text)


def test_ensure_within_and_resolve_signature_matches_backend() -> None:
    assert signature(ui_core.ensure_within_and_resolve) == signature(be_path_utils.ensure_within_and_resolve)
