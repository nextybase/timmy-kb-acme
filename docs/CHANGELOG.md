## [Unreleased] – 2025-11-13
<!-- cspell:ignore configurativo -->
- Unity of the semantic test suite: `build_vocab_db` now covers merge-into aliases, duplicates, canonical-only, plus new DB-first guards (load failure, duplicate alias, merge_into semantics) so every matcher test runs on the real `tags.db`.
- `vision_alignment_check.py` now reads `vision.use_kb`/`vision.strict_output` from `Settings`, logs the chosen source, and applies the configured OpenAI timeout/retries/http2 so the tool mirrors the UI SSoT.
- `vision_alignment_check.py` builds the JSON Schema only when `vision.strict_output` is `true`, otherwise it omits the `text` payload so the check stays as permissive as the UI uptime.
- _Semantic pipeline_ ora conserva l’ordine “first-hit” degli alias in `semantic.vocab_loader` e la suite `tests/test_semantic_extractor.py` gira realmente su `semantic/tags.db` grazie alla fixture `build_vocab_db`, coprendo la traccia DB-first anche per `canonicalOnly`.
- _Vision check_ (`scripts/vision_alignment_check.py`) legge `config/config.yaml` (`vision.model`, `vision.assistant_id_env`, `openai.timeout/max_retries/http2`) e passa i parametri al client: il health-check segue lo stesso SSoT configurativo dell’UI.
- Documentazione e test rimangono allineati: `docs/streamlit_ui.md` descrive il gating condiviso e i test `tests/ui/test_semantics_state.py` restano il riferimento per il messaggio di gating.
