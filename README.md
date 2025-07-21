# 🚀 OnBoarding NeXT – v1.2.3

Benvenuto nel repository ufficiale del sistema di onboarding per il progetto **NeXT**.  
Questa versione (`v1.2.3`) introduce una **naming convention vincolante**, un **logging strutturato e centralizzato**, e una **modularità ancora più leggibile e robusta**.  
La pipeline è ora pronta per l’integrazione di parsing PDF reale, tool di cleaning avanzati, arricchimento AI-driven, e CI/CD.

---

## 📚 Documentazione inclusa

- [`pre_onboarding_readme.md`](./pre_onboarding_readme.md)  
  👉 *Creazione struttura cliente su Google Drive e generazione `config.yaml`.*

- [`onboarding_pipeline_timmy_kb_v1.3.md`](./onboarding_pipeline_timmy_kb_v1.3.md)  
  👉 *Pipeline completa: download PDF ricorsivo, preview Docker e deploy GitHub.*

- [`NAME_LOGGING_RULE.md`](./NAME_LOGGING_RULE.md)  
  👉 *Regole per i nomi di cartelle, file, moduli e funzioni, regole di logging*

---

## 🧭 Obiettivo del progetto

Offrire una pipeline **robusta**, **automatizzata** e **adattiva** per gestire end-to-end il processo di onboarding dei clienti, rendendo i dati immediatamente semantic-ready e AI-friendly.

- ✅ Naming uniforme, logging e modularità garantite
- 🔄 Download ricorsivo PDF e conversione batch in Markdown arricchito (frontmatter semantico)
- 🧪 Anteprima locale KB con Honkit (Docker)
- 🚀 Deploy GitHub con check interattivo ed evitamento duplicazioni
- 🧠 Compatibilità nativa con cloni NeXT (Timmy, ClasScrum, Zeno)
- 🔌 **Separazione totale** tra pipeline core e moduli di arricchimento semantico (NLP/AI)
- 🪵 Logging centralizzato, livelli configurabili, log file e console

---

## 🏁 Flusso operativo

### 🔹 Fase 1: Pre-Onboarding

```bash
py src/pre_onboarding.py
```
Richiede solo slug e nome cliente.  
✔️ Check se cartella esiste già su Drive  
✔️ Validazione struttura YAML e rollback su errore  
✔️ Logging dettagliato di ogni step  
🔎 Dettagli in pre_onboarding_readme.md

---

### 🔹 Fase 2: Onboarding completo

```bash
py src/onboarding_full.py
```
✔️ Caricamento configurazione e check anticipato repo GitHub  
✔️ Download ricorsivo PDF  
✔️ Conversione batch PDF→Markdown arricchito  
✔️ Enrichment semantico automatico  
✔️ Preview Docker con Honkit  
✔️ Push GitHub interattivo o fallback  
✔️ Logging strutturato e feedback CLI  
🔎 Dettagli in onboarding_readme.md

---

### 🔹 Arricchimento semantico (modalità standalone o plug-in pipeline)

```bash
py src/semantic/semantic_extractor.py
```
Conversione e enrichment di tutti i PDF presenti in /raw in markdown con frontmatter semantico.  
Pulizia opzionale e idempotente dei markdown esistenti.  
Rigenerazione automatica di README.md e SUMMARY.md.  
Logging su ogni step critico.  
Nessun rischio di data-loss nella pipeline principale: la cancellazione avviene solo in modalità CLI interattiva.

---

## 🏗 Struttura del repository

```
root/
├── src/
│   ├── pipeline/         # Tutti i moduli core (drive, config, github, content, logging, preview, cleanup)
│   ├── semantic/         # Tutte le funzioni di enrichment, parsing, AI, NLP (semantic_extractor.py, semantic_mapping.py)
│   └── tools/            # Tool CLI standalone di manutenzione (es. cleanup_tool.py, validate_structure_tool.py)
├── config/               # Strutture YAML, mapping semantico cartelle, ecc.
├── output/               # Output generato per ogni cliente (markdown arricchiti, summary, ecc.)
├── .env                  # Variabili di configurazione
├── requirements.txt
└── README.md
```

---

## 🧩 Tecnologie e dipendenze

- Python >= 3.10

**Librerie:**  
PyMuPDF, spacy, pydantic, pyyaml, python-slugify, google-api-python-client, docker, requests, gitpython, PyGithub

**Requisiti extra:**

- Docker installato per preview GitBook
- GitHub CLI (gh) configurato
- Chiave service_account.json per accesso Google Drive

---

## 🪵 Logging e naming rule

Tutto il logging passa da `get_structured_logger` (in logging_utils.py), livelli: DEBUG, INFO, WARNING, ERROR.  
Funzioni, file e variabili in snake_case, nomi parlanti.  
Pipeline pronta per logging JSON e CI/CD.

---

## 🗂️ Changelog sintetico

Consulta il file CHANGELOG.md per tutte le release.

- v1.2.3 – Uniformità naming, logging strutturato, refactor moduli, robustezza orchestrazione
- v1.2.2 – Separazione completa enrichment semantico vs pipeline, conversione PDF batch e frontmatter
- v1.2.1 – Refactoring percorsi e anteprima docker
- v1.2 – Robustezza, rollback, GitHub smart
- v1.1 – Parametrizzazione totale, Google Drive ricorsivo
- v1.0 – Baseline completa
