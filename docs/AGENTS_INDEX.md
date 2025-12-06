# AGENTS Index  Policy Comuni per Agent

Questo indice raccoglie le regole comuni che gli agent devono seguire nel repository. Evitare duplicazioni: i singoli `AGENTS.md` nelle sottocartelle devono contenere solo gli override specifici del loro ambito e rimandare qui per tutto il resto.

## Approccio operativo (AGENT-first, HiTL)

Questo repository tratta l'agente come un *teammate* con responsabilita chiare: le **policy comuni** vivono qui, gli `AGENTS.md` di area definiscono solo **override minimi** e rimandano all'indice. L'approccio e **Human-in-the-Loop**: l'agente propone micro-PR idempotenti, **non** introduce side-effects, e chiude il loop con lint/type/test.

Cardini dell'approccio:
- **SSoT & Safety**  tutte le read/write passano dalle utility e restano nel perimetro del workspace; niente effetti collaterali non dichiarati.
- **Micro-PR**  cambi piccoli, motivati, con diff chiaro; se tocchi X allinea Y/Z (docs, test, frontmatter).
- **Matrix come contratto**  questa tabella e il *punto di verita* tra aree: build/test/lint/path-safety/documentazione sono obblighi, non suggerimenti.
- **Gating UX**  nelle superfici UI le azioni seguono lo **stato** (es. la Semantica si abilita solo con RAW presente), evitando operazioni non idempotenti.

In sintesi: policy **qui**, override **nei loro AGENTS**, e l'agente lavora *on-rails* per garantire coerenza e ripetibilita.


<!-- MATRIX:BEGIN -->
> **Matrice di override (panoramica rapida)**
> Gli `AGENTS.md` locali definiscono solo le deroghe/override; le policy comuni restano in questo indice.

| Area | File | Override chiave (sintesi) | Criteri di accettazione (key) | Note | Task tipici dell'agente |
|------|------|---------------------------|-------------------------------|------|-------------------------|
| Root | `AGENTS.md` | Prima di lavorare rileggi `docs/runbook_codex.md` e i documenti `.codex/` per allineare workflow e standard. | Le attività partono solo dopo avere consultato `docs/runbook_codex.md` e le guide `.codex/`. |  | Allineamento runbook `.codex/`<br>Verifica documenti obbligatori |
| Pipeline Core | `src/pipeline/AGENTS.md` | Path-safety obbligatoria: tutte le write/copy/rm passano da `ensure_within*` (no join manuali).; Scritture atomiche tramite `safe_write_text/bytes`. | Nessuna scrittura fuori dal workspace cliente. |  | Hardening path-safety pipeline<br>Refactor I/O su utility SSoT<br>Log strutturato pipeline/run |
| Semantica | `src/semantic/AGENTS.md` | Uso della facade pubblica `semantic.api`; niente import/invocazioni di funzioni `_private`.; SSoT tag runtime: `semantic/tags.db`; `tags_reviewed.yaml` solo per authoring/migrazione. | Enrichment non duplica tag, rispetta sinonimi/alias e non altera contenuti non frontmatter. |  | Allineamento `semantic.api` vs service<br>Rigenerazione/migrazione `tags.db`<br>Fallback README/SUMMARY idempotenti |
| UI (Streamlit) | `src/ui/AGENTS.md` | Seguire `docs/streamlit_ui.md` per router, stato, I/O e logging; flusso: configurazione -> Drive (provisioning + README + download RAW) -> Semantica (convert/enrich -> README/SUMMARY -> Preview).; Gating: la tab **Semantica** e attiva solo se `raw/` locale esiste. | Nessuna azione "Semantica" se `raw/` e vuoto o mancante. | UX guidata da stato | Refactor orchestratori UI onboarding<br>Audit gating RAW/slug e router `st.navigation`<br>Messaggistica/log `ui.<pagina>` coerente |
| UI (Streamlit) | `src/ui/pages/AGENTS.md` | Versione minima Streamlit 1.50.0 con router nativo obbligatorio (`st.Page` + `st.navigation`); nessun router custom.; Import-safe: niente I/O o side-effect a import; `st.set_page_config` resta centralizzato nell'entrypoint. | Router nativo presente (`st.Page`/`st.navigation`) e link interni via `st.page_link`; query/slug gestiti solo dagli helper dedicati. | UX guidata da stato | Sweep deprecazioni Streamlit 1.50<br>Router nativo `st.Page`/`st.navigation` compliance<br>Path-safety e logging per pagine |
| UI Fine Tuning | `src/ui/fine_tuning/AGENTS.md` | Flusso vincolante: lettura assistant (id, modello, system prompt) in modal read-only con copia/esporta; dry-run con output grezzo; revisione di campi configurabili senza write remota fino a conferma; eventuali export/backup solo nel workspace con I/O atomico.; Modifiche all'Assistant proposte come micro-PR HiTL, con motivazione chiara e diff esplicito. | Il modal System Prompt mostra `assistant_id`, `model`, istruzioni complete e pulsante Copia; il dry-run espone l'output grezzo non alterato. |  | Modal Assistant read-only + export<br>Dry-run con output grezzo<br>Proposte micro-PR per config Assistant |
| Test | `tests/AGENTS.md` | Dataset dummy generati con tool dedicati (mai dati reali).; Nessuna dipendenza di rete: Drive/Git vanno mockati o bypassati. | Build/test verdi in locale; smoke E2E su slug dummy riproducibile. |  | Mock Drive/Git e fixture dummy<br>Contract test su guard `book/`<br>Smoke E2E slug di esempio |
| Documentazione | `docs/AGENTS.md` | Documentazione in italiano; i documenti architetturali possono restare in inglese se dichiarato nell'indice.; Gli aggiornamenti di codice che toccano UX/flow devono riflettersi nei testi nello stesso PR. | Spell check pulito su `docs/` e `README.md` senza ignorati ad hoc. |  | Sweep cSpell e frontmatter versione<br>Allineamento README/docs su nuove feature<br>Aggiornare guide con orchestratori correnti |
| Codex (repo) | `.codex/AGENTS.md` | Path-safety: scrivo solo in `src/`, `tests/`, `docs/`, `.codex/`; mai in `config/**`, `.env*`, `output/**`.; I/O atomico via utility SSoT (`ensure_within*`, `safe_write_*`), nessun side-effect a import-time. | Path-safety rispettata (solo `src/`, `tests/`, `docs/`, `.codex/`; nessuna eccezione). |  | Esecuzione pipeline QA standard<br>Allineamento uso helper GitHub<br>Riuso tool vision/UI condivisi |

<!-- MATRIX:END -->


---

## Policy comuni
- Build
  - Mantieni gli script/target di build idempotenti e ripetibili.
  - Non introdurre effetti collaterali globali o modifiche di stato non dichiarate.
- Test
  - Esegui test locali in modo deterministico; niente dipendenze di rete nei test unit.
  - Usa marker/filtri per isolare aree (es. `-m drive`, `-m push`, `-m slow`).
- Lint & Typecheck
  - Applica i linters configurati (Ruff/Black/isort) e il typecheck (mypy/pyright) quando presenti.
  - Non alterare gli standard del progetto; rispetta le regole gia in `pyproject.toml`.
- path-safety & I/O
  - Qualsiasi lettura/scrittura deve passare dalle utility SSoT (`ensure_within*`, `safe_write_*`).
  - Vietato creare/cancellare file fuori dal perimetro del workspace cliente.
- Documentazione & QA
  - Aggiorna la documentazione quando cambi UX/flow.
  - Mantieni cSpell pulito sulle path previste; aggiorna i dizionari solo per termini tecnici/di dominio.

---

## Rimandi (AGENTS locali)
- Pipeline Core: `src/pipeline/AGENTS.md`
- Semantica: `src/semantic/AGENTS.md`
- UI (Streamlit): `src/ui/AGENTS.md`
- UI (Streamlit): `src/ui/pages/AGENTS.md`
- Test: `tests/AGENTS.md`
- Documentazione: `docs/AGENTS.md`
- Radice progetto: `AGENTS.md`
- Codex (repo): `.codex/AGENTS.md`

---

## Nota anti-duplicazione
- Le sezioni comuni vivono in questo indice.
- I file `AGENTS.md` locali devono contenere solo regole/deroghe specifiche del loro ambito (es. vincoli UI, contratti semantici, piramide test), con un link esplicito a questo indice.
