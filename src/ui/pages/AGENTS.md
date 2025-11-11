# AGENTS.md — Regole vincolanti per `src/ui/pages/` (Streamlit 1.50.0)

> Documento operativo per l’agente che sviluppa/rivede le pagine Streamlit in `src/ui/pages/`.
> Obiettivo: **aderenza rigorosa a Streamlit ≥ 1.50.0**, eliminazione API **deprecated**, UI import-safe, path-safe e osservabile.

---

## 0) Versione & ambito

- **Versione minima**: Streamlit **1.50.0** (il check è hard-fail nell’entrypoint UI) :contentReference[oaicite:0]{index=0}.
- **Router nativo obbligatorio**: `st.Page` e `st.navigation` per build/run delle pagine :contentReference[oaicite:1]{index=1} :contentReference[oaicite:2]{index=2}.
- Le deprecazioni sono sorvegliate da `scripts/dev/check_streamlit_deprecations.py` in CI (vedi §3) :contentReference[oaicite:3]{index=3}.

---

## 1) Architettura delle pagine (contratto non negoziabile)

- **Import-safe**: nessun side-effect al solo import (niente I/O, spawn processi, scritture).
- **Page chrome centralizzato**: non chiamare `st.set_page_config` nelle pagine; è gestito dall’entrypoint (onboarding) :contentReference[oaicite:4]{index=4}.
- **Routing**:
  - Usa **solo** `st.navigation(pages).run()` (niente router custom) :contentReference[oaicite:5]{index=5}.
  - Link interni con `st.page_link(...)`; evita URL manuali/ancore HTML (il guard segnala se mancano) :contentReference[oaicite:6]{index=6}.
- **Query & deep-link**:
  - SSoT client: `st.query_params`, ma passa sempre dagli helper `ui.utils.route_state`/`ui.utils.slug` (get/set tab/slug, rerun ordinato) :contentReference[oaicite:7]{index=7} :contentReference[oaicite:8]{index=8}.
- **Gating coerente**:
  - **ENTRY** abilita **la pagina**; **READY** abilita **preview/finitura** (non mischiare) :contentReference[oaicite:9]{index=9}.
- **I/O path-safe**:
  - Vietati `Path.rglob`, `os.walk`, path manuali: usa `ensure_within_and_resolve`, `iter_pdfs_safe`, `safe_write_text` (atomico) :contentReference[oaicite:10]{index=10} :contentReference[oaicite:11]{index=11}.

---

## 2) UX, stub e componenti UI

- **Dialog/modali**: usa `st.dialog` se disponibile; fallback inline se assente (compat test) :contentReference[oaicite:12]{index=12}.
- **Layout resilienti**: evita `with col:` se lo stub non supporta il context manager; usa helper di colonne/controlli centralizzati (compatibilità test) :contentReference[oaicite:13]{index=13}.
- **Tema**: stile coerente via `.streamlit/config.toml`; per HTML evita `unsafe_allow_html`, preferisci `st.html` per enhancement controllati :contentReference[oaicite:14]{index=14}.

---

## 3) API **deprecate** o **vietate** (Streamlit 1.50.0)

Il guard fallisce se troviamo questi pattern (lista **bloccante**):
- `st.cache(` → usa `st.cache_data`/`st.cache_resource` (il guard le rileva) :contentReference[oaicite:15]{index=15}.
- `st.experimental_*` (qualsiasi) → rimuovere/migrare a equivalenti stabili :contentReference[oaicite:16]{index=16}.
- `unsafe_allow_html=` (su `st.markdown`) → **vietato**: usa `st.html` :contentReference[oaicite:17]{index=17}.
- `use_(container|column)_width=` → non più valido; rimuovere/adeguare il layout nativo :contentReference[oaicite:18]{index=18}.
- Router legacy / hack query: niente `st.experimental_set_query_params`/`get_query_params`; passare dagli helper ufficiali di stato/slug :contentReference[oaicite:19]{index=19}.

Ulteriori guard UI: obbligo presenza `st.Page`/`st.navigation`; divieto `os.walk`/`Path.rglob`; preferenza `st.page_link` (warning in CI) :contentReference[oaicite:20]{index=20} :contentReference[oaicite:21]{index=21} :contentReference[oaicite:22]{index=22}.

---

## 4) Logging & osservabilità

- Logger solo via `get_structured_logger("ui.<pagina>")`. Messaggi brevi (chiave evento), dettagli in `extra`, **zero PII**.
- Vietati `print()` e f-string nel **message** del logger; niente handler duplicati.
- Il guard segnala logger senza prefisso `ui.` nelle pagine :contentReference[oaicite:23]{index=23}.

---

## 5) Errori & fail-fast

- Errori utente **sintetici** (`st.info/warning/error`), dettagli ai log.
- Orchestratori con `finally` per ripristinare gating/stato e non bloccare i pulsanti dopo errori.
- I test contrattuali fotografano le pagine visibili per gate; ogni regressione è **fail** :contentReference[oaicite:24]{index=24}.

---

## 6) Admin & privilegi

- Azioni **admin** (observability, Grafana, ecc.) **solo** in pagine Admin; disabilitate se prerequisiti mancanti (es. Docker down) secondo policy esistente.
- Niente shell-out rumorosi in pagine non-admin; niente redirect automatici post-login (mostrare il pannello) (allineato alle policy UI) :contentReference[oaicite:25]{index=25}.

---

## 7) Checklist PR (bloccante)

1. **Router**: `st.Page`/`st.navigation` presenti; link interni con `st.page_link` :contentReference[oaicite:26]{index=26}.
2. **Deprecazioni**: 0 occorrenze dei pattern di §3 (CI/guard passa) :contentReference[oaicite:27]{index=27}.
3. **Query/slug**: usi esclusivi degli helper `route_state`/`slug`; nessun direct URL parse :contentReference[oaicite:28]{index=28}.
4. **Path-safety/I-O**: niente `rglob/os.walk`; scritture atomiche; helper di workspace corretti :contentReference[oaicite:29]{index=29}.
5. **Logging**: namespace `ui.*`, niente PII/stacktrace utente; nessun `print()` (guard logging) :contentReference[oaicite:30]{index=30}.
6. **Stub compat**: niente `with col:` non supportato; usare fallback modulare per dialog/layout :contentReference[oaicite:31]{index=31} :contentReference[oaicite:32]{index=32}.

---

## 8) Cosa rifiutare (o richiedere fix)

- Introduzione/riuso di API **deprecated**/experimental di Streamlit (vedi §3) :contentReference[oaicite:33]{index=33}.
- Router custom, parsing URL manuale, query-hacks non mediati da helper :contentReference[oaicite:34]{index=34}.
- I/O non sicuro o non atomico; traversal/symlink non gestiti :contentReference[oaicite:35]{index=35}.
- Log con PII o senza prefisso `ui.`; `print()` in UI :contentReference[oaicite:36]{index=36}.

---

### Nota finale
Questo documento rafforza le regole già definite in **docs/streamlit_ui.md** e negli script di guardia (router, path-safety, deprecazioni). Ogni deviazione va motivata con “design note” in PR e proposta di helper per evitare ripetizioni future :contentReference[oaicite:37]{index=37} :contentReference[oaicite:38]{index=38}.
