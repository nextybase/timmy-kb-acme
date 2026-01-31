# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/navigation_spec.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


class PagePaths:
    HOME = "../../ui/pages/home.py"
    NEW_CLIENT = "../../ui/pages/new_client.py"
    MANAGE = "../../ui/pages/manage.py"
    SEMANTICS = "../../ui/pages/semantics.py"
    PREVIEW = "../../ui/pages/preview.py"

    CONFIG_EDITOR = "../../ui/pages/config_editor.py"
    CONFIGURAZIONE = "../../ui/pages/configurazione.py"
    GUIDA = "../../ui/pages/guida_ui.py"
    GUIDA_DEV = "../../ui/pages/guida_dev.py"
    AGENTS_NETWORK = "../../ui/pages/agents_network.py"

    TUNING = "../../ui/pages/tools_check.py"
    SECRETS = "../../ui/pages/secrets_healthcheck.py"  # pragma: allowlist secret
    DIAGNOSTICS = "../../ui/pages/diagnostics.py"
    LOGS_PANEL = "../../ui/pages/logs_panel.py"
    PROTOTIMMY_CHAT = "../../ui/pages/prototimmy_chat.py"
    DUMMY_KB = "../../ui/pages/dummy_kb.py"


@dataclass(frozen=True)
class NavPage:
    path: str
    title: str
    url_path: str | None
    requires: Tuple[str, ...] = ()


@dataclass(frozen=True)
class NavGroup:
    name: str
    pages: Tuple[NavPage, ...]


_NAVIGATION: Tuple[NavGroup, ...] = (
    NavGroup(
        "Onboarding",
        (
            NavPage(PagePaths.HOME, "Home", "home"),
            NavPage(PagePaths.NEW_CLIENT, "Nuovo cliente", "new"),
            NavPage(PagePaths.MANAGE, "Gestisci cliente", "manage"),
            NavPage(PagePaths.SEMANTICS, "Semantica", "semantics", requires=("tags",)),
            NavPage(PagePaths.PREVIEW, "Docker Preview", "preview", requires=("tags",)),
        ),
    ),
    NavGroup(
        "Tools",
        (
            NavPage(PagePaths.CONFIG_EDITOR, "Config Editor", "config"),
            NavPage(PagePaths.DIAGNOSTICS, "Diagnostica", "diagnostics"),
            NavPage(PagePaths.GUIDA, "Guida UI", "guida"),
        ),
    ),
    NavGroup(
        "Admin",
        (
            NavPage(PagePaths.CONFIGURAZIONE, "Configurazione", "configurazione"),
            NavPage(PagePaths.PROTOTIMMY_CHAT, "ProtoTimmy Chat", "prototimmy-chat"),
            NavPage(PagePaths.DUMMY_KB, "Dummy KB (Admin)", "dummy-kb"),
            NavPage(PagePaths.TUNING, "Tuning", "check", requires=("vision",)),
            NavPage(PagePaths.SECRETS, "Secrets Healthcheck", "secrets"),
            NavPage(PagePaths.LOGS_PANEL, "Log dashboard", None),
            NavPage(PagePaths.GUIDA_DEV, "Guida Dev", "guida-dev"),
            NavPage(PagePaths.AGENTS_NETWORK, "Rete degli AGENT", "agents_network"),
        ),
    ),
)

_URL_BY_PATH: Dict[str, str | None] = {page.path: page.url_path for group in _NAVIGATION for page in group.pages}

_REQUIRES_BY_PATH: Dict[str, Tuple[str, ...]] = {
    page.path: page.requires for group in _NAVIGATION for page in group.pages if page.requires
}


def navigation_groups() -> Tuple[NavGroup, ...]:
    """Restituisce la definizione completa dei gruppi di navigazione."""
    return _NAVIGATION


def url_path_for(path: str) -> str | None:
    """Restituisce l'eventuale url_path associato a una pagina."""
    return _URL_BY_PATH.get(path)


def requirements_for(path: str) -> Tuple[str, ...]:
    """Restituisce i gate richiesti per la pagina indicata."""
    return _REQUIRES_BY_PATH.get(path, ())
