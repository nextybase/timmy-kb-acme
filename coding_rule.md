# 📐 Coding & Testing Rules – NeXT/Timmy Pipeline (v1.4)

Versione: v1.4\
Data: 2025-07-25\
Owner: NeXT Dev Team\
Ultima revisione: refactor architettura pipeline / semantic / tools

---

## 🏷️ 1. Naming Convention

**Obiettivo:** garantire coerenza, leggibilità e manutenibilità del codice in tutto l’ecosistema Timmy.

### 1.1 Cartelle

| Dominio                     | Percorso                  | Note                                    |
| --------------------------- | ------------------------- | --------------------------------------- |
| Pipeline strutturale        | `src/pipeline/`           | Solo gestione file, orchestrazione      |
| Moduli semantici            | `src/semantic/`           | Tutte le funzioni AI/annotazione        |
| Strumenti CLI & interfaccia | `src/tools/`              | Refactor, validatori, CLI interattiva   |
| Configurazioni utente       | `config/`                 | Un config globale + uno per cliente     |
| Output client               | `output/timmy-kb-<slug>/` | Contiene anche `config/` cliente        |
| File di test                | `filetest/`               | Organizzati per tipo: pdf/, yaml/, ecc. |
| Script di test              | `tests/`                  | Dev-only, sempre con output dummy       |

Regole di naming cartelle: minuscolo, separazione logica, underscore solo se necessario.

### 1.2 File e Moduli Python

- minuscolo, separatore `_`
- `*_utils.py` per moduli di supporto (non semantici)
- nome descrittivo: vietati `main.py`, `helper.py`, `script.py`
- orchestratori = nome processo (es. `pre_onboarding.py`, `generate_tags_from_pdfs.py`)
- semantic = `semantic_<azione>.py`
- tools = `validate_structure.py`, `refactor_tool.py`, ecc.

### 1.3 Funzioni, Variabili, Costanti

- `snake_case` per tutto
- nome = verbo + oggetto (`extract_keywords`, `build_markdown_index`)
- nessuna variabile one-letter tranne loop `i`, `j`
- costanti: MAIUSCOLO + underscore (`TAG_LIST_PATH`)

### 1.4 Classi

- `PascalCase` obbligatorio
- nome = entità + responsabilità (`PdfExtractor`, `YamlValidator`)

### 1.5 Slug, Output, Repo

- slug cliente: `timmy-kb-<slug>` (es. `timmy-kb-acme`) – minuscolo, no spazi/underscore
- output: `output/timmy-kb-<slug>/`
- repo GitHub: coerente con slug
- markdown: minuscolo, separatori coerenti con frontmatter (no camelCase)

### 1.6 Nuovi moduli / espansione

- Verificare se il dominio già esiste
- Se è semantic, va in `semantic/`; se è interfaccia o strumento, in `tools/`
- Import espliciti e localizzati:

```python
from semantic.keyword_generator import extract_keywords_from_pdf_folder
```

---

## 📝 2. Logging Rules

**Obiettivo:** garantire tracciabilità completa, nessun `print()` fuori da CLI/debug, logging strutturato.

### 2.1 Logging centralizzato

- Modulo unico: `pipeline/logging_utils.py`
- Ogni modulo richiama:

```python
from pipeline.logging_utils import get_logger
logger = get_logger(__name__)
```

### 2.2 Livelli e formato

- `INFO`: step completati con successo (✅)
- `DEBUG`: dettagli interni (solo in dev o verbose)
- `WARNING`: anomalie non bloccanti (⚠️)
- `ERROR`: eccezioni o crash gestiti (❌)

Formato log: `YYYY-MM-DD HH:MM:SS | LIVELLO | modulo | messaggio`

### 2.3 Policy operative

- `print()` ammesso solo in CLI o test
- ogni blocco try-except deve avere `.error()`
- ogni modulo deve avere logger locale
- propagazione abilitata verso file `onboarding.log`
- configurabile via `.env` → log file path + livello default

### 2.4 Esempio

```python
logger.info("✅ Conversione completata: %s", md_path.name)
logger.warning("⚠️ File PDF vuoto: %s", pdf_path)
logger.error("❌ Errore estrazione testo", exc_info=True)
```

---

## 🧪 3. Testing Rules

### 3.1 Struttura

- input: `filetest/pdf/`, `filetest/yaml/`, ...
- test: `tests/<funzione>.py`
- output: `output/timmy-kb-dummytest/`
- cleanup sempre obbligatorio (tranne preview)

### 3.2 Convenzioni

- nessun file test si chiama `test_*.py`
- nomi descrittivi: `test_end2end_dummy.py`, `pdf2md_preview.py`
- test sempre su slug `dummytest`
- idempotenti: run multipli non devono generare conflitti

### 3.3 Policy

- nessun dato reale in `/tests/`
- ogni nuova feature = nuovo script test
- print solo in fase setup/debug

---

## 🧰 4. Policy Semantic Separation

### 4.1 Divisione concettuale

- `pipeline/` = costruzione, orchestrazione, gestione file
- `semantic/` = comprensione, tagging, parsing, chunking, normalizzazione
- `tools/` = validazione struttura, refactor, CLI interattive, funzioni non-core

### 4.2 Keyword extraction client-specific

- ogni cliente genera `timmy_tags.yaml` in `output/timmy-kb-<slug>/config/`
- modulo: `semantic/keyword_generator.py`
- funzione: `extract_keywords_from_pdf_folder()` → lista keyword
- logica: estrazione automatica + validazione umana (HiTL)

Esempio:

```yaml
cliente: acme-srl
keywords_globali:
  - privacy
  - gestione
  - contratto
```

---

## 📘 5. Documentazione & Policy aggiornamento

- Questo file è **l’unica fonte di verità** per naming, logging, testing
- Ogni PR che modifica comportamento architetturale deve aggiornare questo file
- README dei progetti deve sempre linkare qui
- Nuove policy semantic devono essere approvate nel Team C prima di merge

---

## 📚 Allegati

- Esempi in: `pdf2md_preview.py`, `refactor_tool.py`, `onboarding_full.py`
- Esempio validatore: `validate_structure.py`
- Codice AI: in `semantic/` (in arrivo: `rosetta_validator.py`, `semantic_chunker.py`)

