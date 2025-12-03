# Arricchimento semantico - Flusso completo (UI/CLI)

Questa pagina descrive, passo per passo, cosa succede quando avvii l'arricchimento semantico (UI o CLI) e come vengono generati i tag (euristica vs SpaCy).

## 1) Innesco dalla UI
- Pagine coinvolte: `ui.pages.manage` per l'azione "Estrai tag / Avvia arricchimento semantico".
- Handler: `ui.services.tags_adapter.run_tags_update(slug)`.
- Effetti immediati: spinner e risoluzione del contesto cliente (`base_dir`, `raw_dir`, `semantic_dir`) con guardie path-safety.

## 2) Backend di tagging
- Default: `nlp_backend=spacy` (config semantica) o `TAGS_NLP_BACKEND=spacy` da env.
- Fallback automatico: se SpaCy o il modello non sono disponibili, si usa l'euristica path/filename gia esistente.
- Config aggiuntiva:
  - `spacy_model` / `SPACY_MODEL` (default `it_core_news_sm`).
  - Forzare solo l'euristica: `TAGS_NLP_BACKEND=heuristic`.

## 3) Pipeline di estrazione
### 3.1 Euristica (sempre eseguita)
- Modulo: `semantic.auto_tagger` (`_extract_semantic_candidates_heuristic`).
- Sorgenti: segmenti di cartella sotto `raw/` e nome file.
- Scoring: path (peso 1.0) + filename (peso 0.6), stoplist da config, top_k.
- Output per file: `tags`, `score`, `sources` (`path`, `filename`).

### 3.2 SpaCy (se attivo e disponibile)
- Modulo: `semantic.spacy_extractor`.
- Lettura PDF: PyPDF2 (lazy import) per ogni PDF in `raw/`.
- NLP: modello SpaCy configurato -> noun chunks + entita'.
- Mapping aree: `semantic_mapping.yaml`; match keyword/alias su testo e token.
- Scoring: aree e keyword accumulate in un bag ordinato per punteggio, top_k.
- Metadata: entita' e frasi chiave (noun chunks) in `entities` e `keyphrases`.

### 3.3 Merge euristica + SpaCy
- Unione dei candidati: dedup dei tag, somma pesi, merge di entita'/keyphrase, sorgenti arricchite (`sources.spacy` con evidenze/aree).
- Normalizzazione mapping: `semantic.normalizer` applica le regole del mapping cliente.

## 4) Scrittura dei risultati
- Writer CSV: `semantic.auto_tagger.render_tags_csv` -> `semantic/tags_raw.csv` con colonne `relative_path`, `suggested_tags`, `entities`, `keyphrases`, `score`, `sources`.
- README tagging: `semantic.tags_io.write_tagging_readme` aggiorna `semantic/README_TAGGING.md`.
- Persistenza SpaCy in DB: se ci sono evidenze SpaCy, scrive record in `semantic/tags.db` tabella `doc_entities` (`doc_uid` = path relativo del PDF, `area_key`, `entity_id`, `confidence`, `origin=spacy`, `status=suggested`).

## 5) Abilitazione e arricchimento frontmatter
- Dal modal "Revisione keyword (tags_raw.csv)": puoi editare/salvare il CSV.
- "Abilita" chiama `handle_tags_raw_enable`:
  - Genera `tags_reviewed.yaml` e sincronizza `tags.db` (service/stub).
  - Aggiorna lo stato cliente a `arricchito` (se il DB ha termini) o `pronto`.
- Arricchimento frontmatter: `semantic.frontmatter_service.enrich_frontmatter` usa il DB/YAML consolidato.
  - Se in `doc_entities` ci sono tag approved: popola `entities` e `relations_hint` nel frontmatter, usando `doc_uid` come chiave e il mapping Vision per label/relazioni.
- SUMMARY/README: `write_summary_and_readme` produce i file in `book/`.

## 6) Cosa verificare se SpaCy non parte
- Dipendenze: `spacy==3.7.x`, `thinc==8.2.x`, `numpy==1.26.x` (ABI coerente). Modello installato (`python -m spacy download it_core_news_sm`).
- Env/flag: `TAGS_NLP_BACKEND=spacy`; `SPACY_MODEL` coerente con la lingua.
- Log di fallback: `semantic.auto_tagger.spacy_failed` -> usa solo euristica; l'arricchimento continua.

## 7) Configurazioni rilevanti
- `config/config.yaml` (sezione `semantic_defaults`): parametri generali (top_k, stop_tags, lang, nlp_backend, spacy_model).
- `semantic/semantic_mapping.yaml`: aree e alias keyword usati dal motore SpaCy per il match.
- Env override:
  - `TAGS_NLP_BACKEND` (`spacy`/`heuristic`)
  - `SPACY_MODEL` (es. `it_core_news_sm`, `it_core_news_lg`)

## 8) Summary rapido del percorso
1. UI -> `run_tags_update`.
2. Context + paths.
3. Euristica (sempre) + SpaCy (se attivo) -> merge.
4. `tags_raw.csv` + README tagging.
5. Modal "Abilita" -> `tags_reviewed.yaml` / `tags.db`.
6. Arricchimento frontmatter + SUMMARY/README.
7. Se SpaCy manca/fallisce -> fallback euristico, nessun blocco.

## 9) Revisione doc_entities (SpaCy) via CLI
- Backend: `semantic.entities_review` legge/scrive `doc_entities` (tag SpaCy) con status `suggested`/`approved`/`rejected`.
- CLI: `cli/tag_review_cli.py`
  - `python -m cli.tag_review_cli list --db semantic/tags.db` mostra i doc con tag suggested.
  - `python -m cli.tag_review_cli review --db semantic/tags.db --mapping semantic/semantic_mapping.yaml --doc-uid <uid>` per approvare/rifiutare i tag.
- UI future: puo' riusare lo stesso backend (fetch/update) senza logica duplicata.
