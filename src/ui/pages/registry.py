# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/registry.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence

from ui.navigation_spec import NavGroup
from ui.navigation_spec import PagePaths as _PagePaths
from ui.navigation_spec import navigation_groups
from ui.navigation_spec import url_path_for as spec_url_path_for
from ui.utils.stubs import get_streamlit

PagePaths = _PagePaths


def url_path_for(page_path: str) -> str | None:
    return spec_url_path_for(page_path)


@dataclass(frozen=True)
class PageSpec:
    path: str
    title: str
    url_path: str | None


def _to_page_specs(group: NavGroup) -> Sequence[PageSpec]:
    return tuple(PageSpec(page.path, page.title, page.url_path) for page in group.pages)


_PAGE_GROUPS: Dict[str, Sequence[PageSpec]] = {group.name: _to_page_specs(group) for group in navigation_groups()}


def page_specs() -> Mapping[str, Sequence[PageSpec]]:
    """Restituisce la descrizione statica delle pagine per gruppo."""
    return _PAGE_GROUPS


def build_pages() -> Dict[str, List[Any]]:
    """
    Restituisce il dict {gruppo: [st.Page(...), ...]} per st.navigation(...).
    """
    st = get_streamlit()

    def make_page(spec: PageSpec) -> Any:
        kwargs = {"title": spec.title}
        if spec.url_path:
            kwargs["url_path"] = spec.url_path
        return st.Page(spec.path, **kwargs)

    return {group: [make_page(spec) for spec in specs] for group, specs in _PAGE_GROUPS.items()}
