# SPDX-License-Identifier: GPL-3.0-or-later
"""Helper di bootstrap per la dummy KB (path base, PDF vision di fallback)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Callable, Iterable

from pipeline.file_utils import safe_write_bytes

DEFAULT_VISION_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    b"xref\n0 2\n0000000000 65535 f \n0000000010 00000 n \n"
    b"trailer\n<< /Root 1 0 R >>\nstartxref\n9\n%%EOF\n"
)


def client_base(slug: str, repo_root: Path, get_env_var: Callable[[str, str | None], str | None]) -> Path:
    env_root = get_env_var("REPO_ROOT_DIR", default=None)
    if env_root:
        try:
            return Path(env_root).expanduser().resolve()
        except Exception:
            pass
    return repo_root / "output" / f"timmy-kb-{slug}"


def pdf_path(slug: str, repo_root: Path, get_env_var: Callable[[str, str | None], str | None]) -> Path:
    return client_base(slug, repo_root, get_env_var) / "config" / "VisionStatement.pdf"


def build_generic_vision_template_pdf(load_sections: Callable[[], Iterable[dict] | None]) -> bytes:
    """
    Genera un VisionStatement.pdf generico con testo esplicativo per Vision, Mission,
    Framework Etico, Goal e Contesto Operativo. Fallback sul PDF minimale se fallisce.
    """

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4)
        styles = getSampleStyleSheet()
        normal = styles["Normal"]
        heading = styles["Heading2"]

        story: list = []

        def add_title(text: str) -> None:
            story.append(Paragraph(text, heading))
            story.append(Spacer(1, 0.4 * cm))

        def add_paragraph(text: str) -> None:
            story.append(Paragraph(text, normal))
            story.append(Spacer(1, 0.4 * cm))

        story.append(Paragraph("Vision Statement – Template generico", styles["Title"]))
        story.append(Spacer(1, 0.8 * cm))

        sections = load_sections() or []
        if sections:
            ordered = sorted(sections, key=lambda s: float(s.get("order") or 0))
            for section in ordered:
                title = str(section.get("title") or section.get("key") or "Sezione").strip()
                if title:
                    add_title(title)
                description = str(section.get("description") or "").strip()
                if description:
                    add_paragraph(description)
                subsections = section.get("subsections") or section.get("suggested_structure") or section.get("hints")
                if isinstance(subsections, list):
                    for item in subsections:
                        text: str | None = None
                        if isinstance(item, str):
                            text = item.strip()
                        elif isinstance(item, dict):
                            label = str(item.get("label") or item.get("key") or "").strip()
                            desc = str(item.get("description") or "").strip()
                            if label and desc:
                                text = f"{label}: {desc}"
                            else:
                                text = label or desc
                        if text:
                            add_paragraph(text)
        else:
            add_title("Vision")
            add_paragraph(
                "In questa sezione il cliente descrive la propria Vision, ovvero l’orizzonte di lungo periodo "
                "verso cui tende l’organizzazione. La Vision dovrebbe rispondere alla domanda: "
                "«In che tipo di realtà vogliamo contribuire a vivere tra 5–10 anni grazie al nostro lavoro "
                "e all’uso dell’Intelligenza Artificiale?».",
            )
            add_title("Mission")
            add_paragraph(
                "Qui va descritta la Mission, cioè il modo concreto in cui l’organizzazione intende agire "
                "per avvicinarsi alla Vision. La Mission risponde tipicamente a: "
                "«Cosa facciamo, per chi lo facciamo e con quali modalità operative?».",
            )
            add_title("Framework Etico")
            add_paragraph(
                "In questa parte vanno indicati i principi etici che guidano l’uso dell’AI e dei dati: "
                "trasparenza, tracciabilità, supervisione umana, sostenibilità, inclusione, gestione dei bias, "
                "adesione alle normative (es. AI Act) e alle policy interne. "
                "Il Framework Etico deve chiarire quali pratiche sono accettabili e quali no.",
            )
            add_title("Goal (es. orizzonti 3/6/12 mesi)")
            add_paragraph(
                "Qui si definiscono gli obiettivi operativi a breve, medio e lungo termine. "
                "Un possibile schema è quello a basket temporali: ad esempio 3 mesi (attivazione e primi "
                "risultati), 6 mesi (consolidamento e trend), 12 mesi (impatto complessivo e scalabilità)."
            )
            add_paragraph(
                "Per ogni orizzonte temporale è utile indicare obiettivi chiari e, se possibile, alcuni KPI indicativi."
            )
            add_title("Contesto Operativo")
            add_paragraph(
                "In questa sezione il cliente descrive il contesto in cui opera il progetto: "
                "settore di attività (es. PMI, scuola, PA, territorio), tipologia di utenti coinvolti, "
                "lingue di lavoro, normative chiave di riferimento (es. regolamenti di settore, privacy, "
                "linee guida interne). L’obiettivo è fornire al sistema un quadro di riferimento sintetico ma chiaro.",
            )
            add_paragraph(
                "Questo documento funge da contratto semantico tra l’organizzazione e il sistema: "
                "non deve essere perfetto, ma sufficientemente chiaro da permettere di individuare "
                "le aree tematiche principali e gli obiettivi del progetto.",
            )
        doc.build(story)
        return buf.getvalue()
    except Exception:
        return DEFAULT_VISION_PDF


__all__ = ["client_base", "pdf_path", "build_generic_vision_template_pdf", "DEFAULT_VISION_PDF"]


def ensure_dummy_vision_pdf(workspace: Path, *, repo_root: Path | None = None) -> Path:
    """
    Garantisce che esista un VisionStatement.pdf leggibile nel workspace dummy.

    - Se il PDF manca o è vuoto, prova a copiarlo dal template del repo (config/VisionStatement.pdf).
    - Se il template non è presente o non leggibile, genera un PDF minimale di default.
    Ritorna sempre il path del PDF nel workspace.
    """
    pdf_target = workspace / "config" / "VisionStatement.pdf"
    pdf_target.parent.mkdir(parents=True, exist_ok=True)

    def _is_invalid(path: Path) -> bool:
        try:
            return (not path.exists()) or path.stat().st_size <= 0
        except Exception:
            return True

    if _is_invalid(pdf_target):
        repo_root_resolved = repo_root or workspace.parents[2]
        repo_pdf = repo_root_resolved / "config" / "VisionStatement.pdf"
        pdf_bytes: bytes
        if repo_pdf.exists():
            try:
                with repo_pdf.open("rb") as handle:
                    pdf_bytes = handle.read()
            except Exception:
                pdf_bytes = DEFAULT_VISION_PDF
        else:
            pdf_bytes = DEFAULT_VISION_PDF
        try:
            if safe_write_bytes:
                safe_write_bytes(pdf_target, pdf_bytes, atomic=True)
            else:  # pragma: no cover - fallback
                with pdf_target.open("wb") as handle:
                    handle.write(pdf_bytes)
        except Exception:
            # se la scrittura fallisce, lascia invariato il path (fallirà a valle)
            pass
    return pdf_target
