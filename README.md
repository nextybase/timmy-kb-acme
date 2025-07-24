
# 🚀 OnBoarding NeXT – v1.3.3

Benvenuto nel repository ufficiale del sistema di onboarding per il progetto **NeXT**.  
Questa versione (`v1.3.3`) introduce il refactoring architetturale, la centralizzazione della configurazione, la robustezza nei test end-to-end, logging strutturato avanzato e **ALERT su una funzione critica**:

> ⚠️ **ALERT: la funzione di conversione PDF→Markdown non posiziona sempre i file `.md` nella cartella `book/` come previsto.  
> Potrebbero essere generati file markdown in posizioni errate o file extra (.html).  
> Questo bug è noto e verrà risolto con priorità nella release 1.3.4/1.4.  
> Consulta il Changelog e questa sezione per lo stato dei fix e i workaround.**

---

## 📚 Documentazione inclusa

- [`pre_onboarding_readme.md`](./pre_onboarding_readme.md)  
  *Creazione struttura cliente su Google Drive e generazione `config.yaml`.*

- [`onboarding_pipeline_timmy_kb_v1.3.md`](./onboarding_pipeline_timmy_kb_v1.3.md)  
  *Pipeline completa: download PDF ricorsivo, preview Docker e deploy GitHub.*

- [`coding_rule.md`](./coding_rule.md)  
  *Policy e regole ufficiali per naming, logging, convenzioni di test e best practice.*

---

## 🧭 Obiettivo del progetto

Offrire una pipeline **robusta**, **automatizzata**, **adattiva** e **AI-friendly** per gestire end-to-end il processo di onboarding dei clienti, producendo dati già pronti per l’enrichment semantico e la costruzione di knowledge graph.

- **Naming uniforme, logging e modularità garantite**
- **Exception-first**: ogni errore critico solleva un’eccezione custom, mai più errori silenziosi
- **Logging strutturato, centralizzato, pronto per strumenti di ricerca**
- **Download ricorsivo PDF e conversione batch in Markdown arricchito** (frontmatter + tagging semantico)
- **Anteprima locale KB con Honkit (Docker)**
- **Deploy GitHub con check interattivo ed evitamento duplicazioni**
- **Modalità “book-only”**: ora puoi pubblicare su GitHub *solo la knowledge base* già arricchita, senza file temporanei o di configurazione
- **Compatibilità nativa con cloni NeXT** (Timmy, ClasScrum, Zeno)
- **Separazione totale** tra pipeline core e moduli di arricchimento semantico (NLP/AI)
- Tool CLI per refactor e manutenzione batch

---

## ⚠️ ALERT e Limitazioni note (luglio 2025)

- La **funzione di conversione PDF→Markdown** presenta bug che possono portare a:
  - Output dei markdown in cartelle diverse da `book/`.
  - Generazione di file extra (es. `.html`), oppure mancanza di markdown previsti.
- Il team sta lavorando su una soluzione definitiva (fix previsto in v1.3.4/v1.4).
- **Workaround temporaneo:**  
  Verifica la presenza dei markdown nella cartella `book/` e ricontrolla i log di pipeline per path effettivi.
- Apri una issue (o consulta la sezione Changelog) per dettagli su fix e rilascio.

---

## 🏁 Flusso operativo

### 🔹 Fase 1: Pre-Onboarding

```bash
py src/pre_onboarding.py
```

- Richiede solo slug e nome cliente.
- Check se cartella esiste già su Drive.
- Validazione struttura YAML e rollback su errore.
- Logging dettagliato di ogni step.

📖 Dettagli in `pre_onboarding_readme.md`

### 🔹 Fase 2: Onboarding completo

```bash
py src/onboarding_full.py
```

- Caricamento configurazione e check anticipato repo GitHub
- Download ricorsivo PDF
- Conversione batch PDF→Markdown arricchito e tagging semantico
- Enrichment semantico automatico
- Preview Docker con Honkit
- Push GitHub della sola knowledge base (`book/`)
- Logging strutturato e feedback CLI

📖 Dettagli in `onboarding_pipeline_timmy_kb_v1.3.md`

---

### 🔹 Arricchimento semantico (standalone/plug-in)

```bash
py src/semantic/semantic_extractor.py
```
- Conversione e enrichment di tutti i PDF presenti in `/raw` in markdown con frontmatter semantico e tagging.
- Pulizia opzionale e idempotente dei markdown esistenti.
- Rigenerazione automatica di `README.md` e `SUMMARY.md`.
- Logging su ogni step critico.

---

## 🧪 Test & Tools

Tutti gli script di test sono in `/tests/`:

- Test automatici per conversione PDF→Markdown (`tests/pdf2md_preview.py`)
- Test per deploy GitHub (`tests/test_github_utils.py`)
- End-to-end “dummy test” (`tests/test_end2end_dummy.py`) che pulisce, crea, testa e verifica tutto il ciclo onboarding su un cliente fittizio.

Tool CLI in `/src/tools/`:

- `generate_pdf_dummy.py`: genera cartelle e PDF di test per simulazioni end-to-end.
- `cleanup_repo.py`: elimina repo GitHub di test.
- `refactor_tool.py`: base per refactor massivi batch.

Cartella `/filetest/`: contiene i file PDF dummy e altro materiale per i test.

**Best practice:**

- Ogni test genera output in `/output/timmy-kb-dummytest/` (o simile).
- Cleanup finale sempre interattivo.

---

## 🏗 Struttura del repository

```
root/
├── src/
│   ├── pipeline/         # Tutti i moduli core (drive, config, github, content, logging, preview, cleanup, exceptions)
│   ├── semantic/         # Tutte le funzioni di enrichment, parsing, AI, NLP (semantic_extractor.py, semantic_mapping.py)
│   └── tools/            # Tool CLI standalone di manutenzione (es. cleanup_tool.py, refactor_tool.py, validate_structure_tool.py)
├── config/               # Strutture YAML, mapping semantico cartelle, lista tag (timmy_tags.yaml), ecc.
├── output/               # Output generato per ogni cliente (markdown arricchiti, summary, ecc.)
├── filetest/             # File di test organizzati per tipo (pdf/, docx/, ...)
├── tests/                # Script di test (uno per step/funzione, es. test_github_utils.py)
├── .env                  # Variabili di configurazione
├── requirements.txt
├── coding_rule.md
└── README.md
```

---

## 🪵 Logging e gestione errori (novità v1.3.1+)

- Logging centralizzato tramite `get_structured_logger` su tutti i moduli core e semantic.
- Policy emoji e terminologia uniforme (vedi `coding_rule.md`).
- Log file e console sincronizzati, separazione chiara livelli (INFO/WARNING/ERROR).
- Exception-first: errori bloccanti propagati sempre come eccezioni custom, mai più errori “silenziosi” o return booleani.
- Tool CLI per refactor batch e manutenzione (vedi `/tools/`).

---

## 🗂️ Changelog sintetico

Consulta il file `CHANGELOG.md` per tutte le release.

- **v1.3.3** – Refactor architetturale, test end-to-end, bug noto conversione PDF→Markdown (alert)
- **v1.3.2** – Deploy “book-only”, UX step-by-step, robustezza test GitHub, cleaning temp e repo minimale
- **v1.3.1** – Exception-first, logging uniforme, refactor tools, robustezza explainable, policy aggiornata
- **v1.3** – Tagging semantico, robustezza AI-ready, policy di testing e coding centralizzata
- **v1.2.3** – Uniformità naming, logging strutturato, refactor moduli, robustezza orchestrazione
- **v1.2.2** – Separazione completa enrichment semantico vs pipeline, conversione PDF batch e frontmatter
- **v1.2.1** – Refactoring percorsi e anteprima docker
- **v1.2** – Robustezza, rollback, GitHub smart
- **v1.1** – Parametrizzazione totale, Google Drive ricorsivo
- **v1.0** – Baseline completa
