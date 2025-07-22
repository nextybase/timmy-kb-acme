
# 🚀 OnBoarding NeXT – v1.3

Benvenuto nel repository ufficiale del sistema di onboarding per il progetto **NeXT**.  
Questa versione (`v1.3`) introduce il **tagging semantico dei paragrafi**, una nuova convenzione di testing e directory, e la policy ufficiale di coding centralizzata in `coding_rule.md`.  
La pipeline è ora pronta per la generazione automatica di markdown “AI-ready” e la futura integrazione knowledge graph.

---

## 📚 Documentazione inclusa

- [`pre_onboarding_readme.md`](./pre_onboarding_readme.md)  
  👉 *Creazione struttura cliente su Google Drive e generazione `config.yaml`.*

- [`onboarding_pipeline_timmy_kb_v1.3.md`](./onboarding_pipeline_timmy_kb_v1.3.md)  
  👉 *Pipeline completa: download PDF ricorsivo, preview Docker e deploy GitHub.*

- [`coding_rule.md`](./coding_rule.md)  
  👉 *Policy e regole ufficiali per naming, logging, convenzioni di test e best practice (sostituisce il vecchio NAME_LOGGING_RULE.md).*

---

## 🧭 Obiettivo del progetto

Offrire una pipeline **robusta**, **automatizzata**, **adattiva** e **AI-friendly** per gestire end-to-end il processo di onboarding dei clienti, producendo dati già pronti per l’enrichment semantico e la costruzione di knowledge graph.

- ✅ Naming uniforme, logging e modularità garantite
- 🔄 Download ricorsivo PDF e conversione batch in Markdown arricchito (frontmatter + tagging semantico)
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
✔️ Conversione batch PDF→Markdown arricchito e tagging semantico (parola chiave per ogni paragrafo, da YAML ufficiale)  
✔️ Enrichment semantico automatico  
✔️ Preview Docker con Honkit  
✔️ Push GitHub interattivo o fallback  
✔️ Logging strutturato e feedback CLI  
🔎 Dettagli in onboarding_pipeline_timmy_kb_v1.3.md

---

### 🔹 Arricchimento semantico (standalone/plug-in)

```bash
py src/semantic/semantic_extractor.py
```
Conversione e enrichment di tutti i PDF presenti in /raw in markdown con frontmatter semantico e tagging.  
Pulizia opzionale e idempotente dei markdown esistenti.  
Rigenerazione automatica di README.md e SUMMARY.md.  
Logging su ogni step critico.

---

## 🏗 Struttura del repository

```
root/
├── src/
│   ├── pipeline/         # Tutti i moduli core (drive, config, github, content, logging, preview, cleanup)
│   ├── semantic/         # Tutte le funzioni di enrichment, parsing, AI, NLP (semantic_extractor.py, semantic_mapping.py)
│   └── tools/            # Tool CLI standalone di manutenzione (es. cleanup_tool.py, validate_structure_tool.py)
├── config/               # Strutture YAML, mapping semantico cartelle, lista tag (timmy_tags.yaml), ecc.
├── output/               # Output generato per ogni cliente (markdown arricchiti, summary, ecc.)
├── filetest/             # File di test organizzati per tipo (pdf/, docx/, ...)
├── tests/                # Script di test (uno per step/funzione)
├── .env                  # Variabili di configurazione
├── requirements.txt
├── coding_rule.md
└── README.md
```

---

## 🧪 Testing e convenzione cartelle

- Tutti gli script di test si trovano in `/tests/`.
- File di input per i test sono in `/filetest/` con sottocartelle per tipologia (`pdf/`, `docx/`, `yaml/`, ecc.).
- Gli output dei test sono sempre in `/output/timmy-kb-dummytest/`.
- Ogni test termina con la possibilità di cancellare i file generati (cleanup).

Dettagli, naming convention e policy: [coding_rule.md](./coding_rule.md)

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

## 🗂️ Changelog sintetico

Consulta il file CHANGELOG.md per tutte le release.

- v1.3 – Tagging semantico, robustezza AI-ready, policy di testing e coding centralizzata
- v1.2.3 – Uniformità naming, logging strutturato, refactor moduli, robustezza orchestrazione
- v1.2.2 – Separazione completa enrichment semantico vs pipeline, conversione PDF batch e frontmatter
- v1.2.1 – Refactoring percorsi e anteprima docker
- v1.2 – Robustezza, rollback, GitHub smart
- v1.1 – Parametrizzazione totale, Google Drive ricorsivo
- v1.0 – Baseline completa
