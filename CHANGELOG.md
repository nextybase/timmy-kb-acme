# Changelog - Timmy‑KB (Sintesi)

> Formato: [Keep a Changelog](https://keepachangelog.com/it/1.0.0/) · [SemVer](https://semver.org/lang/it/)
>
> Nota: elenco condensato ai soli punti chiave che impattano UX, sicurezza, API pubbliche o qualità.

---

## [1.9.2] - 2025-09-19
### Added
- **Content pipeline**: supporto ai PDF nel root di `raw/` con file aggregato in `book/`.
- **Test**: copertura per root‑PDF, cleanup orfani, encoding SUMMARY, writer CSV hardened, loader vocab fail‑closed.

### Changed
- `pipeline.content_utils`: cleanup idempotente dei `.md` in `book/`; `SUMMARY.md` con percent‑encoding dei link.
- `semantic.auto_tagger.render_tags_csv`: firma con `*, base_dir`, path‑safety forte (`ensure_within_and_resolve` + atomiche); call‑site aggiornati.
- `semantic.vocab_loader`: **fail‑closed** se manca `tags.db`; warning se DB vuoto; info con conteggio canonicals.

### Deprecated
- `semantic.tags_extractor.emit_tags_csv` in favore di `semantic.api.build_tags_csv(...)` o `auto_tagger.render_tags_csv(..., base_dir=...)`.

---

## [fix] — 2025-09-17
### Security
- `semantic/vocab_loader.py`: path‑safety in **lettura** con `ensure_within_and_resolve`.

### Changed
- **Retriever**: `_default_candidate_limit()` come SSoT; `cosine(...)` iterator‑safe.

### Tests
- Unitaria retriever (precedenze `candidate_limit`, casi edge) → **104 passed**.

---

## 2025-09-17 — Smoke tests UI & E2E
### Added
- `scripts/smoke_streamlit_finance.py` (tab **Finanza**) e `scripts/smoke_e2e.py` (E2E headless con push GitHub disabilitato).

### Changed
- UI Finanza: bottone “Importa in finance.db” sempre attivo con gating nell’handler (stabilità test).

---

## [1.10.0] - 2025-09-13
### Added
- **Retriever**: metriche leggere (embed/fetch/score/total ms) + tool `retriever_calibrate.py`.
- **UI**: sidebar “Ricerca (retriever)” con `candidate_limit` e `latency_budget_ms` persistiti in `config.yaml`.

### Changed
- **Path‑safety letture** in `tag_onboarding.py` (hash) e cleanup import.

### Removed / Breaking
- **Fallback semantici** in `semantic.api` (README/SUMMARY/convert): ora **fail‑fast**.
- **Drive adapter**: import “hard” delle dipendenze (errore esplicito se assenti).

---

## [fix] - 2025-09-14
### Changed
- `onboarding_ui.py`: nessun side‑effect a import‑time; tipizzazione e subprocess via `sys.executable`.

### Security
- `finance.api.import_csv`: path‑safety `open_for_read(...)` (traversal mitigato).

---

## [1.8.2] - 2025-09-07
### Added
- `pipeline/path_utils.ensure_within_and_resolve` (SSoT letture sicure) + test traversal/symlink.

### Changed
- Tutte le **letture** in `semantic/*` e `pipeline/*` passano per il wrapper.

---

## [1.8.1] - 2025-09-06
### Added
- Suite test semantica (estrazione, mapping, frontmatter, summary/readme, E2E enrichment).

### Changed
- SSoT contratti: uso `semantic.types.ClientContextProtocol`; SRP e refactor `content_utils`/estrattori.

---

## [1.8.0] - 2025-09-06
### Breaking
- **Formato YAML** unificato; façade `semantic.api` unica; rimosso `semantic_onboarding.py`.

### Added
- `to_kebab()` (SSoT normalizzazione), CLI `src/semantic_headless.py`.

### Changed
- Tipizzazione/ottimizzazioni estrazione semantica; logging ASCII‑only; refactor UI/runner.

### Security
- Path‑safety e scritture atomiche estese (writer README/SUMMARY/MD).

---

## [1.7.0] - 2025-09-01
### Added
- cSpell e script `scripts/fix_mojibake.py`; normalizzazione tipografica docs.

### Changed
- Editor mapping → tab **Configurazione**; struttura `raw/` derivata da `tags_reviewed.yaml`.

---

## [1.6.1] - 2025-08-30
### Added
- Task **CILite**; mypy mirato su `ui`.

### Fixed
- Flake8 a 0; pytest verde su unit+content_utils; pulizia import.

---

## [1.6.0] - 2025-08-29 — Interfaccia Streamlit
### Added
- **UI Streamlit** con tab **Configurazione / Drive / Semantica**; runner Drive; chiusura controllata.

### Changed
- Gating UI (slug/nome); caching stato; preview docker gestita; messaggistica chiara.

### Security
- Path‑safety forte e scritture atomiche in UI/runner.

---

## [1.5.0] - 2025-08-27
### Added
- Suite test PyTest (unit/contract/smoke) + `pytest.ini`; doc test dedicata.

### Changed
- Logging strutturato SSoT; orchestratori snelliti; push GitHub hardening (retry/lease/redazione).

### Security
- Path‑safety `ensure_within` e scritture atomiche su pipeline core.

---

## [1.4.0] - 2025-08-26
### Added
- Preview HonKit/GitBook via Docker; adapter Preview; IO sicure; CI (Qodana/GitHub Actions).

### Changed
- Pipeline contenuti: conversione gerarchica, fingerprint, generatori SUMMARY/README atomici.

### Security
- Rimozione rischi traversal su write/delete; autenticazione GitHub sicura.

---

## [1.3.0] - 2025-08-26
### Changed
- Refactor orchestratori secondo linee guida (funzioni pure testabili; SRP in CSV/enrichment).

### Documentation
- Aggiornate Architecture/Developer/Coding Rules.

---

## [1.2.x] - 2025-08-24/25
### Added
- Nuovi orchestratori (`semantic_onboarding`, poi deprecato); adapter fallback/preview; utility file (atomiche, path‑safety); docs indice `docs/SUMMARY.md`.

### Changed
- Centralizzazione redazione log e path‑safety; tool dummy rigenerato; test dummy/CI di base.

---

## [1.1.0] - 2025-08-23 — Baseline stabile
### Added
- Struttura modulare `src/pipeline/*`; orchestratori `pre_onboarding`, `tag_onboarding`, `onboarding_full`.

### Changed
- Output standard: `output/timmy-kb-<slug>/` (raw, book, semantic, config, logs); documentazione completa iniziale.
