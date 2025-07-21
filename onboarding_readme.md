# 🟩 Onboarding Pipeline Timmy-KB – v1.2.3

Questa è la **pipeline automatizzata** per la creazione della Knowledge Base del cliente Timmy-KB,  
ottimizzata secondo le naming rule e policy di logging della versione 1.2.3.

---

## 📍 Scopo e overview

- **Automatizzare il flusso completo** di ingestione, conversione, enrichment e pubblicazione della documentazione cliente.
- Generazione Knowledge Base pronta per la pubblicazione GitBook/GitHub e per l’arricchimento AI-driven.
- Logging strutturato su ogni step, messaggi CLI chiari e robustezza end-to-end.

---

## ⚙️ Come si usa

### 1. Lancia la pipeline di onboarding

```bash
py src/onboarding_full.py
```
Ti verrà chiesto:

- Lo slug del cliente (deve corrispondere a quello creato in pre-onboarding)

---

### 2. Step principali della pipeline

- **Caricamento config cliente:**  
  Da output/timmy-kb-<slug>/config/config.yaml  
  Logga dettagli config e controlla la presenza di tutti i parametri chiave.

- **Pulizia output:**  
  Chiede conferma se svuotare la cartella output (eccetto config).  
  Nessun rischio di perdita dati, tutto tracciato da log.

- **Download PDF da Google Drive:**  
  Scarica ricorsivamente tutti i PDF dalla cartella cliente su Drive.  
  Mantiene struttura tematica delle sottocartelle.  
  Logging su ogni file scaricato.

- **Conversione batch PDF → Markdown:**  
  Funzione placeholder (in attesa parsing reale in v1.2.4):  
  Crea un markdown fittizio per ogni PDF trovato.  
  Logging per ogni file processato.

- **Arricchimento semantico automatico:**  
  Conversione e arricchimento di tutti i markdown tramite mapping YAML (frontmatter).  
  Rigenerazione README.md e SUMMARY.md.  
  Logging e reporting di successo/errori.

- **Preview locale con Docker (Honkit):**  
  Costruisce e serve la documentazione localmente su http://localhost:4000 tramite Docker.  
  Logging e gestione errori.

- **Deploy su GitHub (opzionale, con conferma CLI):**  
  Push automatico della Knowledge Base sulla repo GitHub del cliente.  
  Evita duplicati e repository incomplete.  
  Logging dettagliato esito deploy.

---

## 🏗️ Struttura cartelle e file coinvolti

```
src/
├── pipeline/
│   ├── drive_utils.py
│   ├── config_utils.py
│   ├── content_utils.py
│   ├── gitbook_preview.py
│   ├── github_utils.py
│   ├── cleanup.py
│   └── logging_utils.py
├── semantic/
│   ├── semantic_extractor.py
│   └── semantic_mapping.py
output/
└── timmy-kb-<slug>/
    ├── config/
    │   └── config.yaml
    ├── raw/
    ├── <cartelle tematiche>/
    ├── README.md
    └── SUMMARY.md
```

---

## 🪵 Logging, naming e orchestrazione

Ogni funzione, file e variabile segue la naming rule snake_case, nessuna abbreviazione oscura.  
Logging sempre centralizzato tramite get_structured_logger (console e file).  
Step batch e processi critici sempre loggati con livello DEBUG, INFO, WARNING, ERROR.  
Tutti gli errori e i warning sono gestiti e riportati all’utente in modo chiaro.

---

## ❗ Novità v1.2.3

- Refactor naming: tutte le funzioni e i file ora seguono la convenzione ufficiale.
- Logging strutturato: ogni step è tracciato, log file e console sempre disponibili.
- Modularità e robustezza: orchestrazione tra pipeline, enrichment e tools ora più chiara e affidabile.
- Preparazione per parsing PDF reale e nuovi moduli AI/CI/CD.

---

## 📎 Note operative

È obbligatorio aver eseguito il pre-onboarding prima di questa pipeline.  
I log sono disponibili sia su console che in logs/onboarding.log.  
Consulta CHANGELOG.md e NAMING_LOGGING_RULES.md per dettagli su tutte le evoluzioni.
