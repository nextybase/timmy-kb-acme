## [Unreleased] — Semantic subsystem refactor & automation readiness

### Contesto
Questa fase di lavoro è stata condotta come Prompt Chain manuale (HiTL), con l’utente umano nel ruolo di “passacarte”, per validare sul campo le regole di governance (ProtoTimmy / OCP / Codex), prima della loro automazione.

### Cosa è stato fatto
- Analisi architetturale completa del repository partendo da MANIFEST.md, con mappatura delle aree funzionali, dei flussi CLI/UI e dei contratti SSoT.
- Analisi approfondita del sottosistema `semantic`, con evidenza dei boundary tra:
  - facade (`semantic.api`)
  - service layer (`convert_service`, `frontmatter_service`, `embedding_service`)
  - domain/persistence (tagging, DB, filesystem).
- Refactor mirato e non funzionale:
  - introduzione di `semantic.paths.get_semantic_paths` come utility neutra;
  - eliminazione di dipendenze inverse service → facade;
  - rimozione di import underscore da `semantic.api` in file non-test;
  - spostamento di `build_tags_csv` in `semantic.tagging_service` con delega retro-compatibile da `semantic.api`.
- Rafforzamento del safety net:
  - aggiornamento test per usare il seam reale (`semantic.paths`);
  - nuovi test deterministici su artefatti di tagging (README_TAGGING.md, tags.db / doc_entities).
- Esecuzione completa della test suite:
  - `pytest -q`: 855 passed, 10 skipped, 3 deselected.
- Formalizzazione della decisione architetturale tramite ADR-0005.

### Cosa NON è stato fatto (intenzionalmente)
- Nessun cambiamento funzionale o di comportamento osservabile.
- Nessuna modifica a schema DB, UX CLI/UI, pipeline non-semantic.
- Nessuna automazione di governance (ADR trigger, Evidence persistence, dispatcher runtime).

### Stato attuale
- Il sottosistema semantic è strutturalmente più pulito e testato.
- Le regole di governance (Prompt Chain, Gate, HiTL) sono validate manualmente.
- Il sistema è **READY FOR AUTOMATION: medium**.

### Prossimi passi (intenzioni)
- Avviare una nuova Prompt Chain focalizzata su:
  - enforcement runtime di allowed_actions e fasi;
  - dispatcher / control plane OCP;
  - persistence delle evidenze (Evidence Gate, QA Gate, HiTL ack);
  - standardizzazione run_id / trace_id end-to-end.
- Questa fase potrà includere refactor anche sostanziosi, ma solo dopo planning formale.

## [Unreleased]  2025-11-13
<!-- cspell:ignore configurativo -->
- Hardening sicurezza: lettura di `tags_raw.json` in `kg_builder` ora usa `read_text_safe` con path validato (niente `Path.read_text` diretto) per rispettare i vincoli path-safety.
- Migrazione namespace: rimosso il pacchetto/alias legacy `timmykb.*`; tutti gli import usano ora i moduli locali (`ingest`, `pipeline.*`, `semantic.*`, `ui.*`). Preflight aggiornato per segnalare solo la coerenza dei moduli pipeline.
- Logging/osservabilita: logger UI centralizzato (`.timmykb/logs/ui.log` con propagazione), redazione estesa (token/secret/password/key/service_account) e Promtail che etichetta anche `run_id`/`trace_id`/`span_id` per i log UI; gli entrypoint CLI (`pre_onboarding`, `tag_onboarding`, `onboarding_full`) aprono ora trace root OTEL per la correlazione Grafana/Tempo; `log_viewer` mostra anche righe non strutturate.
- BREAKING (Vision): `semantic.vision_provision.provision_from_vision` richiede ora sempre `model` esplicito (UI/CLI passano `get_vision_model()`); rimosso il fallback implicito e il flag `force` verso il layer semantic. Aggiornare eventuali caller custom/tool esterni.
- Unity of the semantic test suite: `build_vocab_db` now covers merge-into aliases, duplicates, canonical-only, plus new DB-first guards (load failure, duplicate alias, merge_into semantics) so every matcher test runs on the real `tags.db`.
- Vision provisioning riallineato allo health-check: `use_kb` segue ENV/Settings/config (default True) e le `run_instructions` abilitano File Search solo quando il flag e attivo.
- `vision_alignment_check.py` now reads `vision.use_kb`/`vision.strict_output` from `Settings`, logs the chosen source, and applies the configured OpenAI timeout/retries/http2 so the tool mirrors the UI SSoT.
- `vision_alignment_check.py` builds the JSON Schema only when `vision.strict_output` is `true`, otherwise it omits the `text` payload so the check stays as permissive as the UI uptime.
- `vision_alignment_check.py` registra `vision_alignment_check.strict_output` con `value`/`source` e include `strict_output` + `response_format` nell'output JSON; i nuovi `tests/tools/test_vision_alignment_check.py` coprono i casi config vs default.
- Il payload Vision ora aggiunge `assistant_id` e `assistant_id_source` (log `vision_alignment_check.assistant_id`), migliorando la tracciabilita dei fallimenti dell'assistente.
- Il JSON e i log del tool Vision riportano ora anche `assistant_env`/`assistant_env_source`, e un nuovo test CLI (`test_assistant_missing_reports_missing`) garantisce che lo scenario senza assistant resti visibile come missing.
- `build_vocab_db` ora rispetta la numerazione `pos` corrente in `tag_synonyms` (usa `MAX(pos)+1` come base) e mantiene l'ordine first-hit anche quando la fixture viene rilanciata con alias duplicati o merge successivi.
- _Semantic pipeline_ ora conserva l'ordine first-hit degli alias in `semantic.vocab_loader` e la suite `tests/test_semantic_extractor.py` gira realmente su `semantic/tags.db` grazie alla fixture `build_vocab_db`, coprendo la traccia DB-first anche per `canonicalOnly`.
- _Vision check_ (`tools/vision_alignment_check.py`) legge `config/config.yaml` (`ai.vision.model`, `ai.vision.assistant_id_env`, `ai.openai.timeout/max_retries/http2`) e passa i parametri al client: il health-check segue lo stesso SSoT configurativo dellUI.
- Documentazione e test rimangono allineati: `docs/streamlit_ui.md` descrive il gating condiviso e i test `tests/ui/test_semantics_state.py` restano il riferimento per il messaggio di gating.
- Gating Semantica e Drive logging sono stati rinforzati per strumenti da runbook: `_require_semantic_gating` ricalcola `has_raw_pdfs` anche quando riusa lo stato cache, svuota la cache se i PDF scompaiono e solleva `RuntimeError`, `tests/ui/test_semantics_state.py` coprono la rivisitazione e il nuovo path raw, mentre `src/ui/pages/manage.py`/`src/ui/manage/drive.py` registrano `ui.manage.drive.*` (diff/readme/piano/download) e validano `SERVICE_ACCOUNT_FILE` prima di abilitare il download con un test dedicato (`tests/ui/test_manage_drive.py`).
- QA: suite completa `python -m pytest -q` verde su Windows (10 skipped per symlink non supportati); pre-commit pulito dopo normalizzazione Markdown.
