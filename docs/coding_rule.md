# Timmy‑KB — Coding Rules (v1.6.1)

Linee guida per contribuire al codice in modo coerente, sicuro e manutenibile.

> **Doppio approccio:** puoi lavorare da **terminale** (orchestratori in sequenza) **oppure** tramite **interfaccia (Streamlit)**.  
> Avvio interfaccia: `streamlit run onboarding_ui.py` — vedi [Guida UI (Streamlit)](guida_ui.md).

---

## Principi
- **SSoT** (Single Source of Truth): riusa utilità già presenti; evita duplicazioni.
- **Idempotenza**: ogni step deve poter essere rieseguito senza effetti collaterali.
- **Path‑safety**: nessuna write/copy/rm senza passare da utility di sicurezza.
- **Fail‑fast & messaggi chiari**: errori espliciti e log azionabili.
- **Compatibilità cross‑platform**: Windows/Linux (path, encoding, newline).

---

## Struttura & naming
- **Slug** e nomi cartelle: normalizza con `to_kebab()` dove previsto.
- **RAW/BOOK/SEMANTIC**: non cambiare convenzioni senza aggiornare orchestratori e documentazione.
- **File generati**: mantieni posizionamento in `output/timmy-kb-<slug>/...`.

---

## Python style
- **Tipizzazione** obbligatoria sui moduli core: annota parametri e ritorni. Usa `Optional[...]` in modo esplicito.
- Evita `Any` e i *wild import*; mantieni import espliciti e ordinati.
- Funzioni corte, una responsabilità; preferisci pure functions quando possibile.
- Non introdurre side‑effects in import‑time (es.: I/O o letture env al top‑level).

---

## Typing & Pylance
- Per dependency opzionali usa *narrowing* esplicito:
  - `if fn is None: raise RuntimeError("...")` prima di chiamare funzioni opzionali.
  - Wrapper utili tipo `_require_callable(fn, name)` nei layer adapter/runner.
- Evita accessi a metodi su `None` (es. `.strip`): usa normalizzatori tipo `_norm_str`.
- Streamlit: preferisci API **stabili** (`st.rerun`) con fallback controllato a `experimental_*` se assente.

---

## Logging & redazione
- Usa il **logger strutturato** dove disponibile; fallback a `logging.basicConfig` negli script.
- Redazione automatica attiva quando richiesto (`LOG_REDACTION`): non loggare segreti o payload completi.
- Includi `event` e metadati essenziali (slug, conteggi, esiti) per ogni operazione rilevante.

---

## Sicurezza I/O
- **Path‑safety**: usa `ensure_within_and_resolve` (o equivalenti SSoT) per evitare traversal; mai concatenare path manualmente.
- **Scritture atomiche**: utilizza `safe_write_text/bytes` per generare/aggiornare file (niente write parziali).
- **Sanitizzazione nomi file**: usa utility dedicate prima di creare file da input esterni.

---

## Orchestratori & UI
- Orchestratori (`pre_onboarding`, `tag_onboarding`, `semantic_onboarding`, `onboarding_full`):
  - Niente input bloccanti nei moduli di servizio; tutta la UX rimane negli orchestratori.
  - Gestisci `--non-interactive` per batch/CI.
- UI (`onboarding_ui.py`):
  - Gating a **due input** (slug, nome cliente), poi mostra le tab.
  - **Drive**: crea struttura → genera README → **download su raw**.
  - **Semantica**: conversione → arricchimento → README/SUMMARY → preview (opz.).
  - Usa `_safe_streamlit_rerun()` per compatibilità con diversi stub/tipi.

---

## Error handling & exit codes
- Solleva eccezioni tipizzate (es. `ConfigError`, `PreviewError`), non `Exception` generiche.
- Mappa le eccezioni a **exit codes** coerenti negli script CLI.
- In UI mostra errori con messaggi chiari e non verbosi; logga il dettaglio tecnico.

---

## Drive & Git
- **Drive**: tutte le operazioni passano da `pipeline/drive_utils.py` o runner dedicati; evita chiamate dirette alle API *low‑level*.
- **Download RAW**: usa la funzione di alto livello esposta nel runner UI.
- **Git**: push solo di `.md` in `book/`; ignora `.md.fp` e file binari.

---

## Test
- Genera dataset **dummy** con `py src/tools/gen_dummy_kb.py --slug dummy`.
- Piramide: unit → middle/contract → smoke E2E (dummy). Niente dipendenze di rete nei test.
- Mocka Drive/Git nei test; verifica invarianti su `book/` e presenza di README/SUMMARY.

---

## Versioning & release
- **SemVer** + `CHANGELOG.md` (Keep a Changelog).
- Aggiorna **README** e i documenti in `docs/` quando cambi UX/flow.
- Tag/branch coerenti con la policy di versione (vedi `versioning_policy.md`).

---

## Contributi
- PR piccole, atomic commit, messaggi chiari (imperativo al presente).
- Copri con test i cambi di comportamento; mantieni l’asticella della qualità.
- Evita duplicazioni: se serve una nuova utility, valuta prima i moduli esistenti.
