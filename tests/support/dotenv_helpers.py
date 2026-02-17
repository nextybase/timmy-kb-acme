# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pipeline.env_utils as envu
from tests.determinism.env_helpers import reload_module, write_dotenv


def prepare_dotenv_env(
    *,
    monkeypatch,
    tmp_path: Path,
    env_text: str,
    clear_keys: Iterable[str],
):
    """Setup condiviso per test dotenv: file, cwd, env pulita, reload lazy-loader."""
    write_dotenv(tmp_path, env_text)
    for key in clear_keys:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    reload_module(envu)
    envu.ensure_dotenv_loaded()
    return envu
