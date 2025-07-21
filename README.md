# 🚀 OnBoarding NeXT – v1.2.2

Benvenuto nel repository ufficiale del sistema di onboarding per il progetto **NeXT**.  
Questa versione (`v1.2.2`) consolida la **separazione tra pipeline di produzione e arricchimento semantico**, introduce un sistema di conversione batch PDF→Markdown arricchito, e prepara la base per la futura integrazione di modelli AI/NLP.

---

## 📚 Documentazione inclusa

- [`pre_onboarding_readme.md`](./pre_onboarding_readme.md)  
  👉 *Creazione struttura cliente su Google Drive e generazione `config.yaml`.*

- [`onboarding_pipeline_timmy_kb_v1.3.md`](./onboarding_pipeline_timmy_kb_v1.3.md)  
  👉 *Pipeline completa: download PDF ricorsivo, preview Docker e deploy GitHub.*

---

## 🧭 Obiettivo del progetto

Offrire una pipeline **robusta**, **automatizzata** e **adattiva** per gestire end-to-end il processo di onboarding dei clienti, rendendo i dati immediatamente semantic-ready e AI-friendly.

- ✅ Creazione cartelle su Drive con validazione e rollback
- 🔄 Download ricorsivo dei PDF e conversione in Markdown arricchiti (con frontmatter semantico)
- 🧪 Anteprima locale della KB con Honkit (Docker)
- 🚀 Deploy GitHub con check interattivo ed evitamento duplicazioni
- 🧠 Compatibilità nativa con cloni NeXT (Timmy, ClasScrum, Zeno)
- 🔌 **Separazione totale** tra pipeline core e moduli di arricchimento semantico (NLP/AI)

---

## 🏁 Flusso operativo

### 🔹 Fase 1: Pre-Onboarding

```bash
py src/pre_onboarding.py
```

Richiede solo slug e nome cliente.  
✔️ Check se cartella esiste già su Drive  
✔️ Validazione struttura YAML e rollback su errore  
🔎 Dettagli in pre_onboarding_readme.md

---

### 🔹 Fase 2: Onboarding completo

```bash
py src/onboarding_full.py
```

✔️ Check anticipato se la repo GitHub esiste già  
✔️ Download ricorsivo PDF  
✔️ Conversione batch PDF→Markdown arricchito (con frontmatter semantico)  
✔️ Preview Docker con Honkit  
✔️ Push GitHub interattivo o fallback  

🔎 Dettagli in onboarding_readme.md

---

### 🔹 Arricchimento semantico (modalità standalone o plug-in pipeline)

```bash
py src/semantic/semantic_extractor.py
```

- Conversione di tutti i PDF presenti in `/raw` in markdown con frontmatter semantico.
- Pulizia opzionale e idempotente dei markdown esistenti.
- Rigenerazione automatica di `README.md` e `SUMMARY.md`.
- Nessun rischio di data-loss nella pipeline principale: la cancellazione avviene solo in modalità CLI interattiva.

---

## 🏗 Struttura del repository

```
root/
├── src/
│   ├── ingest/          # Pipeline e moduli di base (drive, pdf, config, push, ecc.)
│   ├── semantic/        # Tutte le funzioni di enrichment, parsing, AI, NLP (semantic_extractor.py, semantic_mapping.py)
│   └── utils/           # Logging, helpers, config writers, ecc.
├── config/              # Strutture YAML, mapping semantico cartelle, ecc.
├── output/              # Output generato per ogni cliente (markdown arricchiti, summary, ecc.)
├── .env                 # Variabili di configurazione
├── requirements.txt
└── README.md
```

---

## 🧩 Tecnologie e dipendenze

- Python >= 3.10
- **Librerie:** PyMuPDF, spacy, pydantic, pyyaml, python-slugify, google-api-python-client, docker, requests

**Requisiti extra:**

- Docker installato per preview GitBook
- GitHub CLI (gh) configurato
- Chiave service_account.json per accesso Google Drive

---

## 🗂️ Changelog sintetico

Consulta il file CHANGELOG.md per tutte le release.

- **v1.2.2** – Separazione completa enrichment semantico vs pipeline, conversione PDF batch e frontmatter
- **v1.2.1** – Refactoring percorsi e anteprima docker
- **v1.2** – Robustezza, rollback, GitHub smart
- **v1.1** – Parametrizzazione totale, Google Drive ricorsivo
- **v1.0** – Baseline completa

