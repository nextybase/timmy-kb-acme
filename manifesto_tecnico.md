# 📘 Manifesto Tecnico – KB Semantica Onboarding Timmy (v1.0)

## 🎯 Finalità Generale
La Knowledge Base (KB) semantica di Timmy è progettata come base informativa strutturata per ogni organizzazione onboardata attraverso la pipeline NeXT. Ogni contenuto caricato, convertito e annotato, contribuisce a una rappresentazione formalizzata della conoscenza aziendale, leggibile sia da esseri umani che da modelli AI.

## ✅ Obiettivi Non Negoziali
1. Strutturazione accessibile all’AI: ogni `.md` deve avere frontmatter YAML e sezioni marcate semanticamente.
2. Parsabilità semantica per blocco: i paragrafi devono essere annotati con `<!-- tags: [...] -->`.
3. Coerenza semantica globale: struttura coerente slug_cliente → categoria → documento.
4. Linearità di parsing: ogni inferenza euristica deve essere comunicata e sottoposta a validazione umana (HiTL). La semantica deve essere dichiarata, non dedotta.
5. Tracciabilità e accountability: ogni `.md` deve riportare origine del dato e trasformazioni subite.
6. Modularità e atomicità: ogni `.md` è indipendente, aggiornabile e chunkizzabile.
7. Compatibilità con DB vettoriali: i contenuti devono essere segmentabili per embedding semantico.

## 🔧 Separazione delle Responsabilità

> **Separazione tra pipeline (costruzione, IO) e semantica (arricchimento, parsing, tag):**

- `pipeline/`  
  - File system, path, orchestrazione, conversione base.
  - **No semantica, tagging, inferenza.**

- `semantic/`  
  - Arricchimento semantico, tagging, mapping, normalizzazione, estrazione chunk e keyword.
  - **In repo**: `semantic_extractor.py`, `semantic_mapping.py`  
  - **Da aggiungere**: `semantic_chunker.py`, `rosetta_validator.py`, `keyword_generator.py`

- `tools/`  
  - Refactoring, validazione, cleaning, CLI, manutenzione (presente e allineata).

## 🛠️ Manuale Moduli – stato reale del repo

### Orchestratori (`src/`)
- `onboarding_full.py` (presente)
- `pre_onboarding.py` (presente)

### Pipeline (`src/pipeline/`)
- `config_utils.py`
- `file2md_utils.py`
- `logging_utils.py`
- `gitbook_preview.py`
- `drive_utils.py`
- `cleanup.py`
- `content_utils.py`
- `github_utils.py`

### Semantic (`src/semantic/`)
- `semantic_extractor.py`
- `semantic_mapping.py`
- (da implementare: `semantic_chunker.py`, `rosetta_validator.py`, `keyword_generator.py`)

### Tools (`src/tools/`)
- `refactor_tool.py`: refactoring batch e sostituzioni massive
- `validate_structure.py`: validazione schema e struttura yaml/raw
- `cleanup_repo.py`: pulizia repo e ambienti dev
- `gen_dummy_kb.py`: generazione Knowledge Base dummy

### Tests (`tests/`)
- `test_config_utils.py`: test funzionalità di configurazione e validazione file
- `test_end2end.py`: test end-to-end della pipeline
- `pdf2md_preview.py`: test e preview della conversione PDF→Markdown
- `test_gitbook_preview.py`: test anteprima e validazione output GitBook/Honkit
- `test_github_utils.py`: test delle funzioni di utilità per GitHub

> Tutti questi strumenti e test garantiscono **qualità**, **non regressione** e **robustezza** della pipeline e dei tool associati.


## 🧭 Architettura Funzionale
- **Livello 0:** Sandbox AI  
- **Livello 1:** KB documentale statico (GitBook / Honkit)
- **Livello 2:** Parsing + vector KB (chunk/tag/embedding/indicizzazione)
- **Livello 3:** Dashboard semantica (Streamlit/NextJS + validazione umana)

## 🔄 Flusso Operativo
1. Pre-onboarding: struttura + config
2. Pre-semantica: estrazione testo/tag (da realizzare modulo)
3. Onboarding: conversione PDF→.md
4. Annotazione: tagging, mapping categorie (semantic)
5. Validazione umana (GitBook/Dashboard)
6. Parsing AI → DB vettoriale
7. Interrogazione (bot/prompt/query)

## 🧩 Interfaccia `.md` semantico (standard)
- Frontmatter YAML: titolo, categoria, slug_cliente, origine_cartella, origine_file, tags globali, data_conversione, stato_normalizzazione
- Sezioni: titoli `##`
- Annotazioni: `<!-- tags: [...] -->`

## 🔍 Principi di Progettazione
- Annotazione automatica + validazione HiTL
- Separazione markup/interpretazione
- Compatibilità strumenti authoring/parsing
- Flessibilità, robustezza e modularità
- Pipeline ispezionabile, componibile, adattabile

## 📌 Prossimi Step Strategici
- Formalizzazione standard `.md` semantico
- Implementazione `rosetta_validator.py`
- Costruzione libreria categorie/tag
- Design dashboard validazione
- Refactor pipeline per pieno rispetto manifesto

---

**Nota**: I moduli da implementare sono già previsti nella roadmap, la struttura del repo è allineata, e il processo di validazione file/config è stato integrato e testato.

