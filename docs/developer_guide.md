# Guida Sviluppatore – Timmy-KB

Questa guida fornisce tutte le informazioni necessarie per comprendere l’architettura, contribuire allo sviluppo e mantenere **Timmy-KB** in linea con le best practice aziendali e open-source. È basata su `architecture.md`, `coding_rule.md` e sullo storico evolutivo del progetto (`CHANGELOG.md`).

---

## 📂 Struttura del repository

```txt
root/
 ├── src/
 │   ├── pre_onboarding.py      # orchestratore fase 0 (interattivo di default)
 │   ├── onboarding_full.py     # orchestratore end-to-end (interattivo di default)
 │   ├── pipeline/              # moduli core (drive, github, utils, logging, eccezioni, costanti, …)
 │   ├── semantic/              # estrazione/mapping semantico e post-processing
 │   └── tools/                 # utility CLI, validatori, refactoring
 ├── config/                     # YAML (cartelle_raw.yaml, mapping, template)
 ├── output/                     # output Markdown/YAML generati
 ├── tests/                      # unit + end-to-end
 └── docs/                       # documentazione

```

## 🧩 Architettura tecnica

### Livelli funzionali
1. **Livello 0 – Sandbox AI**: area sperimentale per test e prototipi.
2. **Livello 1 – KB documentale statico**: generazione contenuti per GitBook/Honkit.
3. **Livello 2 – Parsing + KB vettoriale**: estrazione e indicizzazione per ricerca semantica.
4. **Livello 3 – Dashboard semantica**: interfaccia avanzata di consultazione.

### Componenti principali
- **src/**: orchestratori (`pre_onboarding.py`, `onboarding_full.py`) che avviano i passi della pipeline (validazione config, download RAW, conversione PDF→MD, preview, push).  
- **src/pipeline/**: moduli core per la **costruzione** dei file e i servizi di pipeline (es. `content_utils.py`, `github_utils.py`, `drive_utils.py`, `path_utils.py`, `logging_utils.py`, `constants.py`, `exceptions.py`).  
- **src/semantic/**: componenti di arricchimento semantico (`semantic_extractor.py`, `semantic_mapping.py`).  
- **src/tools/**: utility CLI e supporto (es. `refactor_tool.py`, `gen_dummy_kb.py`).

---

## ⚙️ Regole di sviluppo (estratto da coding_rule.md)

- **Naming & Struttura**: seguire schema fisso cartelle, file di supporto con `_utils.py`, no camelCase nei nomi file.
- **Funzioni**: no variabili globali (tranne costanti), CLI con `argparse`.
- **Logging**: esclusivamente tramite `pipeline/logging_utils.py`, formati `INFO`, `DEBUG`, `WARNING`, `ERROR`.
- **Test**: organizzati in `tests/`, preferire test end-to-end, no dati sensibili.
- **Separazione semantica**: orchestrazione in `src/`, logica semantica in `semantic/`.

---

## 🔄 Flusso operativo

### 1. Pre-Onboarding
- Configura slug progetto e nome cliente.
- Genera config iniziali e struttura cartelle.

### 2. Popolamento contenuti
- Caricamento PDF nel Google Drive, organizzati in sottocartelle per tipologia.

### 3. Onboarding Full
- Parsing documenti.
- Arricchimento semantico: estrazione keyword, tagging, normalizzazione.
- Generazione KB con frontmatter YAML.
- Preview Docker (Honkit) → conferma con **INVIO**.
- Scelta se procedere con push GitHub.

---

## 🧪 Testing

```bash
pytest tests/ --maxfail=1 --disable-warnings -q
```
- Test core bloccanti per moduli chiave.
- Output test in `output/timmy-kb-dummy/`.

---

## 📈 Stato evolutivo

Dalla versione `0.9.0-beta` a `1.0.0`:
- Refactoring moduli `semantic/` e `tools/`.
- Logging centralizzato completato.
- Workflow GitHub Actions attivo.
- Documentazione riorganizzata in `docs/`.

---

## 🛠 Strumenti e integrazioni
- **Docker Honkit** → preview locale.
- **GitHub Actions** → CI/CD.
- **Validator semantico** → controllo qualità contenuti.

---

## 📚 Risorse utili
- [Architettura tecnica](architecture.md)
- [Guida utente](user_guide.md)
- [Regole di codifica](coding_rule.md)
- [Contributing](../CONTRIBUTING.md)
