## [Unreleased] – 2025-11-13
<!-- cspell:ignore configurativo -->
- _Semantic pipeline_ ora conserva l’ordine “first-hit” degli alias in `semantic.vocab_loader` e la suite `tests/test_semantic_extractor.py` gira realmente su `semantic/tags.db` grazie alla fixture `build_vocab_db`, coprendo la traccia DB-first anche per `canonicalOnly`.
- _Vision check_ (`scripts/vision_alignment_check.py`) legge `config/config.yaml` (`vision.model`, `vision.assistant_id_env`, `openai.timeout/max_retries/http2`) e passa i parametri al client: il health-check segue lo stesso SSoT configurativo dell’UI.
- Documentazione e test rimangono allineati: `docs/streamlit_ui.md` descrive il gating condiviso e i test `tests/ui/test_semantics_state.py` restano il riferimento per il messaggio di gating.
