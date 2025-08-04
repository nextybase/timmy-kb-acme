
# 📐 Coding & Testing Rules – NeXT/Timmy Pipeline (v1.0)

**Versione:** v1.0  
**Data:** 2025-08-04  
**Owner:** NeXT Dev Team  
**Ultima revisione:** allineamento repository & naming

---

## 🏷️ 1. Naming Convention

**Obiettivo:** garantire coerenza, leggibilità e manutenibilità del codice in tutto l’ecosistema Timmy.

### 1.1 Cartelle

| Dominio                     | Percorso                  | Note                                    |
|-----------------------------|---------------------------|-----------------------------------------|
| Pipeline strutturale        | `src/pipeline/`           | Solo gestione file, orchestrazione      |
| Moduli semantici            | `src/semantic/`           | Tutte le funzioni AI/annotazione        |
| Strumenti CLI & interfaccia | `src/tools/`              | Refactor, validatori, CLI interattiva   |
| Configurazioni utente       | `config/`                 | Un config globale + uno per cliente     |
| Output client               | `output/timmy-kb-<slug>/` | Contiene anche `config/` cliente        |
| Output test                 | `output/timmy-kb-dummy/`  | Output generato dai test automatici     |
| Script di test              | `tests/`                  | Dev-only, output sempre su dummy        |

- Regole di naming cartelle: minuscolo, separazione logica, underscore solo se necessario.

### 1.2 File e Moduli Python

- Minuscolo, separatore `_`
- `*_utils.py` per moduli di supporto (non semantici)
- Nome descrittivo: vietati `main.py`, `helper.py`, `script.py`
- Orchestratori = nome processo (es. `pre_onboarding.py`, `generate_tags_from_pdfs.py`)
- Semantic = `semantic_<azione>.py`
- Tools = `validate_structure.py`, `refactor_tool.py`, ecc.

### 1.3 Funzioni, Variabili, Costanti

- `snake_case` per tutto
- Nome = verbo + oggetto (`extract_keywords`, `build_markdown_index`)
- Nessuna variabile one-letter tranne loop `i`, `j`
- Costanti: MAIUSCOLO + underscore (`TAG_LIST_PATH`)

### 1.4 Classi

- `PascalCase` obbligatorio
- Nome = entità + responsabilità (`PdfExtractor`, `YamlValidator`)

### 1.5 Slug, Output, Repo

- Slug cliente: `timmy-kb-<slug>` (es. `timmy-kb-acme`) – minuscolo, no spazi/underscore
- Output: `output/timmy-kb-<slug>/`
- Output test: `output/timmy-kb-dummy/`
- Repo GitHub: coerente con slug
- Markdown: minuscolo, separatori coerenti con frontmatter (no camelCase)

### 1.6 Nuovi moduli / espansione

- Verificare se il dominio già esiste
- Se è semantic, va in `semantic/`; se è interfaccia o strumento, in `tools/`
- Import espliciti e localizzati:

  ```python
  from semantic.keyword_generator import extract_keywords_from_pdf_folder
  ```

---

## 📝 2. Logging Rules

**Obiettivo:** garantire tracciabilità completa, nessun print() fuori da CLI/debug, logging strutturato.

### 2.1 Logging centralizzato

- Modulo unico: `pipeline/logging_utils.py`
- Ogni modulo richiama:

  ```python
  from pipeline.logging_utils import get_structured_logger
  logger = get_structured_logger(__name__)
  ```
  *(Nota: il nome della funzione logger viene sempre allineato al repo, non alle policy teoriche)*

### 2.2 Livelli e formato

- **INFO:** step completati con successo (✅)
- **DEBUG:** dettagli interni (solo in dev o verbose)
- **WARNING:** anomalie non bloccanti (⚠️)
- **ERROR:** eccezioni o crash gestiti (❌)

- **Formato log:** `YYYY-MM-DD HH:MM:SS | LIVELLO | modulo | messaggio`

### 2.3 Policy operative

- `print()` ammesso solo in CLI o test
- Ogni blocco try-except deve avere `.error()`
- Ogni modulo deve avere logger locale
- Propagazione abilitata verso file `onboarding.log`
- Configurabile via `.env` → log file path + livello default

### 2.4 Esempio

```python
logger.info("✅ Conversione completata: %s", md_path.name)
logger.warning("⚠️ File PDF vuoto: %s", pdf_path)
logger.error("❌ Errore estrazione testo", exc_info=True)
```

---

## 🧪 3. Testing Rules

### 3.1 Struttura

- test: `tests/test_<funzione>.py`
- output: `output/timmy-kb-dummy/`
- cleanup sempre obbligatorio (tranne preview)

### 3.2 Convenzioni

- I file di test iniziano con `test_` (compatibilità pytest) o altro nome descrittivo purché non ambiguo
- Test sempre su slug dummy
- Test idempotenti: run multipli non devono generare conflitti

### 3.3 Policy

- Nessun dato reale in `/tests/`
- Ogni nuova feature = nuovo script test
- Print solo in fase setup/debug

---

## 🧰 4. Policy Semantic Separation

### 4.1 Divisione concettuale

- `pipeline/` = costruzione, orchestrazione, gestione file
- `semantic/` = comprensione, tagging, parsing, chunking, normalizzazione
- `tools/` = validazione struttura, refactor, CLI interattive, funzioni non-core

### 4.2 Keyword extraction client-specific

- Ogni cliente genera `timmy_tags.yaml` in `output/timmy-kb-<slug>/config/`
- Modulo: `semantic/keyword_generator.py` (in roadmap)
- Funzione: `extract_keywords_from_pdf_folder()` → lista keyword
- Logica: estrazione automatica + validazione umana (HiTL)

**Esempio:**

```yaml
cliente: acme-srl
keywords_globali:
  - privacy
  - gestione
  - contratto
```

---

## 📘 5. Documentazione & Policy aggiornamento

- Questo file è l’unica fonte di verità per naming, logging, testing
- Ogni PR che modifica comportamento architetturale deve aggiornare questo file
- README dei progetti deve sempre linkare qui
- Nuove policy semantic devono essere approvate nel Team C prima di merge

---

## 📚 Allegati

- Esempi: `pdf2md_preview.py`, `refactor_tool.py`, `onboarding_full.py`
- Esempio validatore: `validate_structure.py`
- Codice AI: in `semantic/` (in arrivo: `rosetta_validator.py`, `semantic_chunker.py`)
