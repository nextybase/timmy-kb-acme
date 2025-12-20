# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/agents_network.py
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable, Dict, List, Protocol, Tuple, cast

from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from ui.chrome import render_chrome_then_require
from ui.utils.docs_view import load_markdown, render_markdown
from ui.utils.repo_root import get_repo_root
from ui.utils.stubs import get_streamlit

st = get_streamlit()
LOGGER = get_structured_logger("ui.agents_network")


class CachedMarkdownFn(Protocol):
    def __call__(self, rel_path: str) -> str: ...

    def clear(self) -> None: ...


CacheDecorator = Callable[[Callable[[str], str]], CachedMarkdownFn]
cache_markdown = cast(CacheDecorator, st.cache_data(show_spinner=False))


# ---------------------------------------------------------------------------
# Modello dati: rete AGENTS
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentNode:
    area: str
    file_label: str
    rel_path: str


@dataclass(frozen=True)
class AgentsTree:
    areas: Dict[str, List[AgentNode]]


@dataclass(frozen=True)
class MarkdownSection:
    heading: str
    body: str


@cache_markdown
def _read_markdown(rel_path: str) -> str:
    """
    Lettura sicura e cacheata di un file Markdown relativo alla root del repo.
    Ritorna un messaggio di warning in caso di errore.
    """
    try:
        repo_root = get_repo_root()
        return cast(str, load_markdown(repo_root / rel_path))
    except Exception as exc:  # pragma: no cover - degradazione di sicurezza
        LOGGER.warning(
            "ui.agents_network.read_markdown_failed",
            extra={"rel_path": rel_path, "error": str(exc)},
        )
        return f"Impossibile leggere `{rel_path}`.\n\nDettagli: {exc}"


def _extract_matrix_block(md: str) -> List[str]:
    """
    Estrae il blocco della matrice AGENTS tra <!-- MATRIX:BEGIN --> e <!-- MATRIX:END -->.
    Se i marker non sono presenti, ritorna tutte le righe come fallback.
    """
    lines = md.splitlines()
    in_block = False
    block: List[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("<!-- MATRIX:BEGIN"):
            in_block = True
            continue
        if stripped.startswith("<!-- MATRIX:END"):
            in_block = False
            break
        if in_block:
            block.append(line)

    return block or lines


def _normalise_rel_path(cell: str) -> str:
    """
    Converte il contenuto della colonna 'File' in un path relativo dal root del repo.
    - Se contiene '/', viene usato così com'è (es. 'src/ui/pages/AGENTS.md').
    - Se è solo 'AGENTS.md', viene interpretato come file alla root.
    """
    text = cell.strip().strip("`").strip()
    if not text:
        return "AGENTS.md"
    if "/" in text:
        return text
    return text


def _parse_agents_index(md: str) -> AgentsTree:
    """
    Parsea system/ops/agents_index.md e costruisce una struttura Area -> [AgentNode].
    Si appoggia alla matrice principale (righe Markdown con '|').
    """
    raw_block = _extract_matrix_block(md)

    areas: Dict[str, List[AgentNode]] = {}
    for line in raw_block:
        stripped = line.strip()
        # righe utili: iniziano con '|' e hanno almeno 5 colonne (header incluso)
        if not stripped.startswith("|"):
            continue
        if "Area" in stripped and "File" in stripped:
            # header
            continue
        if stripped.startswith("|------"):
            # separatore tabella
            continue

        # | Area | File | Override ... |
        parts = [col.strip() for col in stripped.split("|")]
        if len(parts) < 4:
            continue

        area = parts[1].strip()
        file_cell = parts[2].strip()
        if not area or not file_cell:
            continue

        rel_path = _normalise_rel_path(file_cell)
        node = AgentNode(area=area, file_label=file_cell, rel_path=rel_path)
        areas.setdefault(area, []).append(node)

    return AgentsTree(areas=areas)


# ---------------------------------------------------------------------------
# Helpers Markdown per editor sezionale
# ---------------------------------------------------------------------------


def _split_markdown_sections(raw: str) -> List[MarkdownSection]:
    """
    Suddivide un Markdown in sezioni di livello 1 (# ).
    heading: testo del titolo senza '#'
    body: testo fino al prossimo heading (senza includere il titolo)
    """
    lines = raw.splitlines()
    sections: List[MarkdownSection] = []
    current_heading: str | None = None
    current_body: List[str] = []

    def flush() -> None:
        nonlocal current_heading, current_body
        if current_heading is not None:
            sections.append(MarkdownSection(heading=current_heading, body="\n".join(current_body).rstrip()))
        current_heading = None
        current_body = []

    for line in lines:
        if line.startswith("# "):
            flush()
            current_heading = line[2:].strip()
            continue
        if current_heading is not None:
            current_body.append(line)

    flush()
    return sections


def _join_markdown_sections(sections: List[MarkdownSection]) -> str:
    """
    Ricompone le sezioni in un Markdown completo.
    Ogni sezione ha forma:
    # heading
    body
    (righe vuote tra sezioni, newline finale unica)
    """
    parts: List[str] = []
    for section in sections:
        heading = section.heading.strip()
        body = section.body.rstrip()
        parts.append(f"# {heading}")
        if body:
            parts.append(body)
        parts.append("")  # separatore vuoto
    if parts and parts[-1] == "":
        parts = parts[:-1]
    return "\n\n".join(parts) + "\n"


def _load_agents_text(rel_path: str) -> str:
    repo_root = get_repo_root()
    safe_path = ensure_within_and_resolve(repo_root, repo_root / rel_path)
    return cast(str, read_text_safe(safe_path.parent, safe_path, encoding="utf-8"))


def _save_agents_sections(rel_path: str, sections: List[MarkdownSection]) -> None:
    repo_root = get_repo_root()
    safe_path = ensure_within_and_resolve(repo_root, repo_root / rel_path)
    payload = _join_markdown_sections(sections)
    safe_write_text(safe_path, payload, encoding="utf-8", atomic=True)
    LOGGER.info(
        "ui.agents_network.section_saved",
        extra={"rel_path": rel_path, "sections": len(sections)},
    )


# ---------------------------------------------------------------------------
# Matrice AGENTS
# ---------------------------------------------------------------------------


def _regenerate_agents_matrix() -> None:
    """
    Richiama lo script di rigenerazione della matrice AGENTS.
    """
    repo_root = get_repo_root()
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    try:
        from tools import gen_agents_matrix
    except Exception as exc:  # pragma: no cover - import fallback
        LOGGER.warning(
            "ui.agents_network.matrix_regen_import_failed",
            extra={"error": str(exc)},
        )
        st.error("Impossibile importare tools/gen_agents_matrix.py. Controlla i log.")
        return

    try:
        gen_agents_matrix.main(check=False)

        # Invalida la cache del reader Markdown per riflettere subito i cambiamenti
        try:
            _read_markdown.clear()
        except Exception:
            LOGGER.warning("ui.agents_network.cache_clear_failed")

        st.success("Matrice AGENTS rigenerata. " "Ricorda di committare anche system/ops/agents_index.md.")
        LOGGER.info(
            "ui.agents_network.matrix_regenerated",
            extra={"rel_path": "system/ops/agents_index.md"},
        )
    except SystemExit as exc:
        LOGGER.warning(
            "ui.agents_network.matrix_regen_failed",
            extra={"rel_path": "system/ops/agents_index.md", "code": exc.code},
        )
        st.error("Rigenerazione matrice AGENTS fallita. Verifica i log e riprova.")
    except Exception as exc:  # pragma: no cover - degradazione
        LOGGER.warning(
            "ui.agents_network.matrix_regen_failed",
            extra={"rel_path": "system/ops/agents_index.md", "error": str(exc)},
        )
        st.error("Errore durante la rigenerazione della matrice AGENTS. Controlla i log.")


# ---------------------------------------------------------------------------
# Modal per visualizzare/modificare Markdown
# ---------------------------------------------------------------------------


def _supports_dialog() -> bool:
    dlg = getattr(st, "dialog", None)
    return callable(dlg)


def _inject_wide_dialog_css() -> None:
    html_fn = getattr(st, "html", None)
    if not callable(html_fn):
        return
    html = """
    <style>
    /* Forza il dialog ad occupare ~80% della viewport (container e contenuto) */
    section[data-testid="stDialog"],
    section[data-testid="stDialog"] > div:first-child,
    div[role="dialog"],
    div[role="dialog"] > div,
    div[data-testid="stModalContent"],
    div[data-testid="stModalContent"] > div:first-child {
        width: 80vw !important;
        max-width: 80vw !important;
        min-width: 80vw !important;
    }
    /* Garantisce che il contenuto interno non restringa il dialog */
    section[data-testid="stDialog"] > div {
        width: 100% !important;
    }
    </style>
    """
    html_fn(html)


def _open_markdown_modal(title: str, rel_path: str, *, editable: bool = True) -> None:
    """
    Apre un modal (se supportato) o degrada a render inline mostrando il contenuto
    Markdown del file richiesto, con editor sezionale.
    """
    LOGGER.info("ui.agents_network.modal_open", extra={"rel_path": rel_path})

    try:
        raw_md = _load_agents_text(rel_path)
        sections = _split_markdown_sections(raw_md)
    except Exception as exc:  # pragma: no cover - degradazione di sicurezza
        LOGGER.warning(
            "ui.agents_network.read_markdown_failed",
            extra={"rel_path": rel_path, "error": str(exc)},
        )
        raw_md = _read_markdown(rel_path)
        sections = []

    if _supports_dialog():
        dialog_builder = cast(
            Callable[[str], Callable[[Callable[[], None]], Callable[[], None]]], getattr(st, "dialog")
        )

        @dialog_builder(f"Dettaglio - {title}")
        def _modal() -> None:
            _inject_wide_dialog_css()
            st.markdown(f"### {title}")

            if not editable:
                render_markdown(st, raw_md)
                return

            if not sections:
                st.info(
                    "Editor sezionale non disponibile: il file non contiene intestazioni di livello 1 ('# '). "
                    "Mostro il contenuto in sola lettura."
                )
                render_markdown(st, raw_md)
                return

            for idx, section in enumerate(sections):
                col_title, col_save = st.columns([0.75, 0.25])
                with col_title:
                    st.markdown(f"### {section.heading}")
                with col_save:
                    save_clicked = st.button(
                        "💾 Salva sezione",
                        key=f"{rel_path}::{idx}::save",
                    )
                body_key = f"{rel_path}::{idx}::body"
                new_body = st.text_area(
                    label="",
                    value=section.body,
                    key=body_key,
                    height=220,
                )

                if save_clicked:
                    try:
                        latest = _load_agents_text(rel_path)
                        latest_sections = _split_markdown_sections(latest)
                        if idx < len(latest_sections):
                            latest_sections[idx] = MarkdownSection(
                                heading=latest_sections[idx].heading,
                                body=new_body,
                            )
                            _save_agents_sections(rel_path, latest_sections)
                            st.success(
                                "Sezione salvata (ricorda di aggiornare la matrice AGENTS "
                                "se cambiano Regole/Accettazione)."
                            )
                        else:
                            st.warning("Indice sezione non valido; ricarica e riprova.")
                    except Exception as exc:  # pragma: no cover - degradazione
                        LOGGER.warning(
                            "ui.agents_network.section_save_failed",
                            extra={"rel_path": rel_path, "error": str(exc)},
                        )
                        st.error("Errore nel salvataggio della sezione. Controlla i log.")

        _modal()
    else:
        # Fallback inline
        st.markdown(f"### {title}")
        render_markdown(st, raw_md)


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------


def _render_agents_tree(tree: AgentsTree) -> None:
    """
    Colonna sinistra: mappa ad albero degli AGENT derivata da system/ops/agents_index.md.
    Niente box apri/chiudi: ogni area è una radice e i file sono mostrati come rami,
    ciascuno con il proprio pulsante per aprire la scheda in un modal.
    """
    st.markdown("#### Rete degli AGENT (da AGENTS_INDEX)")
    st.caption(
        "Mappa ad albero delle aree e dei relativi `AGENTS.md`. "
        "Clicca su un file per aprire la scheda completa in un modal."
    )

    if not tree.areas:
        st.warning(
            "Non riesco a leggere la matrice in `system/ops/agents_index.md`. "
            "Controlla che i marker MATRIX siano presenti e ben formattati."
        )
        return

    # Ordina le aree per avere una struttura stabile e leggibile
    for area in sorted(tree.areas.keys()):
        nodes = tree.areas[area]
        if not nodes:
            continue

        # Radice dell'albero
        st.markdown(f"**{area}**")

        # Foglie (file) con prefisso grafico ├── / └──
        for idx, node in enumerate(nodes):
            is_last = idx == len(nodes) - 1
            prefix = "└──" if is_last else "├──"

            col_prefix, col_button = st.columns([0.10, 0.90])
            with col_prefix:
                # prefisso ad albero in monospace
                st.markdown(f"`{prefix}`")
            with col_button:
                if st.button(
                    node.file_label,
                    key=f"agent_node::{area}::{node.rel_path}",
                ):
                    _open_markdown_modal(
                        title=f"{area} – {node.file_label}",
                        rel_path=node.rel_path,
                    )

        # separatore visivo tra aree
        st.markdown("---")


def _render_codex_docs_panel() -> None:
    """
    Colonna destra: documenti chiave per Codex e la rete degli agent.
    - runbook Codex
    - guida integrazione Codex
    - documenti .codex (CONSTITUTION, WORKFLOWS, PROMPTS, CHECKLISTS, AGENTS)
    """
    st.markdown("#### Documenti Codex & integrazione")
    st.caption(
        "Accesso rapido ai documenti che governano l’integrazione di Codex e la rete degli agent. "
        "Ogni pulsante apre il relativo Markdown."
    )

    st.markdown("**Runbook & integrazione**")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Runbook Codex", key="doc_runbook_codex"):
            _open_markdown_modal(
                title="Runbook Codex",
                rel_path="system/ops/runbook_codex.md",
                editable=False,
            )
    with col2:
        if st.button("Guida Codex", key="doc_codex_guide"):
            _open_markdown_modal(
                title="Integrazione Codex",
                rel_path="system/specs/guida_codex.md",
                editable=False,
            )

    st.markdown("---")
    st.markdown("**Documenti di governance `.codex/`**")

    codex_docs: List[Tuple[str, str, str]] = [
        ("Constitution", ".codex/CONSTITUTION.md", "Costituzione operativa per Codex & agent."),
        ("Workflows", ".codex/WORKFLOWS.md", "Flussi tecnici e operativi orchestrati dall'agente."),
        ("Checklists", ".codex/CHECKLISTS.md", "Checklist operative per QA, sicurezza e PR."),
        ("PROMPTS", ".codex/PROMPTS.md", "API mentale di Codex, entrypoint e macro-task."),
        ("AGENTS (.codex)", ".codex/AGENTS.md", "Regole specifiche per l'agente Codex nel repo."),
    ]

    for label, rel_path, desc in codex_docs:
        if st.button(label, key=f"codex_doc::{rel_path}"):
            _open_markdown_modal(title=label, rel_path=rel_path, editable=False)
        if desc:
            st.caption(desc)


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------


# Header + sidebar coerenti con le altre pagine admin-like; slug NON obbligatorio.
render_chrome_then_require(allow_without_slug=True)

st.subheader("Rete degli AGENT & integrazione Codex")
st.caption(
    "Vista amministrativa della rete degli agent e dei documenti che governano "
    "l'integrazione di Codex. Questa pagina consente sia la navigazione sia "
    "l'editing sezionale degli AGENTS; funzionalità di editing avanzato "
    "arriveranno in step successivi."
)

# Layout a due colonne: sinistra (albero AGENTS), destra (documenti Codex)
col_left, col_right = st.columns([2, 1])

with col_left:
    if st.button("↻ Aggiorna matrice AGENTS", key="regen_agents_matrix"):
        _regenerate_agents_matrix()

    agents_index_md = _read_markdown("system/ops/agents_index.md")
    tree = _parse_agents_index(agents_index_md)
    _render_agents_tree(tree)

with col_right:
    _render_codex_docs_panel()
