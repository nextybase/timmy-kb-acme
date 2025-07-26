# Timmy-KB – Onboarding Pipeline v1.3.3

---

# Timmy-KB: Knowledge Base Onboarding Pipeline (v1.3.3)

Pipeline modulare, automatizzata e AI-ready per l’onboarding strutturato di PMI nella piattaforma NeXT (Nested eXtreme Timeline), con generazione semantica di knowledge base in Markdown e pubblicazione continua su GitHub/GitBook.

> Questa versione è la release **1.3.3** e conclude il refactoring architetturale della 1.3.

---

## 🎯 Scopo

- Automatizzare l’onboarding documentale e operativo di clienti (PMI o organizzazioni)
- Generare una **Knowledge Base** semantica, pulita e pubblicabile in formato Markdown
- Centralizzare la configurazione dell’ambiente via `.env` e `config/`
- Consentire test end-to-end, preview Docker e deploy GitHub senza passaggi manuali

## 🧩 Architettura (overview)

- **Pipeline modulare:** separazione rigorosa tra moduli di pipeline, semantica e strumenti (`/pipeline`, `/semantic`, `/tools`)
- **Configurazione centralizzata:** tutte le variabili principali sono gestite da `pipeline/settings.py` e dal file `.env`
- **Onboarding in step idempotenti:**
    - Pre-onboarding (setup cartelle, creazione Drive, config cliente)
    - Onboarding full (download PDF, conversione Markdown, enrichment semantico, preview Docker, push GitHub)
- **Output knowledge base semantico:** tutti i markdown generati sono raccolti in una sola cartella `book/`, pronta per la pubblicazione (output “flat”)
- **Preview locale e deploy:** preview via Docker/Honkit su `book/`, push GitHub solo della knowledge base pulita

## 🏗️ Struttura delle cartelle

```
project-root/
├── output/
│   └── timmy-kb-<slug>/
│       ├── raw/         # PDF originali scaricati da Drive
│       ├── book/        # Tutti i Markdown generati (knowledge base pulita)
│       └── config/      # File config cliente
├── src/
│   ├── pipeline/
│   ├── semantic/
│   └── tools/
├── filetest/
│   └── ...              # Risorse di test/dummy
├── logs/
│   └── ...
└── .env
```

## ⚙️ Prerequisiti

- Python 3.10+
- Docker (per preview locale)
- Account Google Drive + service account JSON
- Token GitHub con permessi repo
- Variabili configurate in `.env` (vedi sotto)

## ⚡ Setup rapido

1. **Clona il repository e installa le dipendenze**
2. **Configura `.env`** (esempio):
    ```env
    DRIVE_ID=...
    GOOGLE_SERVICE_ACCOUNT_JSON=...
    GITHUB_ORG=nextybase
    GITHUB_TOKEN=...
    ```
3. **Esegui il pre-onboarding:**
    ```sh
    py src/pre_onboarding.py
    ```
   Segui i prompt per slug e nome cliente. Verrà creata la struttura Drive e il file `config.yaml` cliente.
4. **Popola la cartella Drive** con i PDF richiesti (secondo le sottocartelle generate).
5. **Esegui l’onboarding completo:**
    ```sh
    py src/onboarding_full.py
    ```
   La pipeline effettuerà download, conversione, enrichment, preview e (opzionale) deploy GitHub della knowledge base.


## 🧪 Test e strumenti di sviluppo

- **Test end-to-end**: `tests/end2end_dummy.py` simula tutta la pipeline su un cliente di test, dalla creazione delle cartelle al push GitHub.
- **Generazione PDF dummy**: `src/tools/generate_pdf_dummy.py` crea PDF di esempio tematici per ogni cartella (configurabili in YAML).
- **Cleanup completo**: `src/tools/cleanup_repo.py` rimuove tutto l’output e le repo di test di un cliente.


## 🪵 Logging e debug

- Ogni modulo scrive log dettagliati sia su console sia su file dedicato in `logs/` (es. `logs/onboarding.log`)
- In caso di errori gravi (es. config mancante, Docker non attivo), la pipeline si interrompe e avvisa chiaramente
- Tutte le interazioni non di sistema sono solo via logger o prompt CLI


## 📝 Changelog sintetico

- **v1.3.3** (2025-07-26): Refactor architetturale, test end-to-end, bug noto conversione PDF→Markdown (alert)
- **v1.3.2** (2025-07-18): Output KB only, deploy GitHub ottimizzato, patch directory temporanee
- **v1.3.1** (2025-07-13): Logging strutturato, refactor naming, CLI interattive idempotenti
- **v1.3.0** (2025-07-10): Prima versione modulare onboarding NeXT (architettura stabile)


## 📚 Documentazione e principi

- **Regole di coding:** vedere `regole_coding_pipeline.md` per naming, logging, test, modularità
- **Manifesto tecnico:** principi semantici e architetturali in `manifesto_tecnico_kb_timmy.md`
- **Roadmap operativa:** milestones e step successivi in `ProgettoRoadmap1_3.pdf`

---

### 🟢 Per ogni dubbio, segui la documentazione e le regole di coding interne. Per bug, segnala su GitHub (con log e dettagli del caso).

