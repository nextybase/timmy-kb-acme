# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Iterable

import pipeline.env_utils as envu


def prepare_dotenv_env(
    *,
    monkeypatch,
    tmp_path: Path,
    env_text: str,
    clear_keys: Iterable[str],
):
    """Setup condiviso per test dotenv: file, cwd, env pulita, reload lazy-loader."""
    (tmp_path / ".env").write_text(env_text, encoding="utf-8")
    for key in clear_keys:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    importlib.reload(envu)
    loaded = envu.ensure_dotenv_loaded()
    if not loaded:
        importlib.reload(envu)
        envu.ensure_dotenv_loaded()
    return envu
