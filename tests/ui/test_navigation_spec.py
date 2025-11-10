# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from ui.navigation_spec import navigation_groups


def _iter_pages():
    for group in navigation_groups():
        for page in group.pages:
            yield page


def test_navigation_paths_are_unique() -> None:
    seen = set()
    for page in _iter_pages():
        assert page.path not in seen
        seen.add(page.path)


def test_navigation_url_paths_unique_when_set() -> None:
    seen = {}
    for page in _iter_pages():
        if page.url_path is None:
            continue
        assert page.url_path not in seen
        seen[page.url_path] = page.path
