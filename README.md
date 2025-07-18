
# 🚀 OnBoarding NeXT – v1.2

Benvenuto nel repository ufficiale del sistema di onboarding per il progetto **NeXT**.  
Questa versione (`v1.2`) introduce coerenza tra pre-onboarding e onboarding, path dinamici centralizzati via `.env`, logging robusto, controlli di idempotenza e un'infrastruttura scalabile e AI-ready.

---

## 📚 Documentazione inclusa

- [`pre_onboarding_readme.md`](./pre_onboarding_readme.md)  
  👉 *Guida alla creazione iniziale della struttura cliente su Google Drive e generazione del file di configurazione (`config.yaml`).*

- [`onboarding_pipeline_timmy_kb_v1.2.md`](./onboarding_pipeline_timmy_kb_v1.2.md)  
  👉 *Guida alla pipeline completa: conversione documenti (download PDF ricorsivo), preview su Docker e deploy GitHub.*

Entrambe le fasi sono modulari, validate manualmente e pienamente integrabili in CI/CD.

---

## 🧭 Obiettivo del progetto

Offrire una pipeline **robusta**, **automatizzata** e **adattiva** per gestire end-to-end il processo di onboarding dei clienti:

- ✅ Creazione cartelle su Drive e struttura di configurazione iniziale
- 🔄 Download ricorsivo dei PDF e conversione in Markdown + JSON semantici
- 🧪 Anteprima locale della KB con Honkit (Docker)
- 🚀 Deploy automatizzato su GitHub (pubblico o privato)
- 🧠 Compatibilità nativa con cloni NeXT (es. Timmy, ClasScrum, Zeno)

---

## 🧱 Struttura generale

```
project-root/
├── config/                         # Configurazioni generali (es. struttura Drive)
├── clienti/                        # (Opzionale) Copia dei config cliente
├── output/                         # Output generato (Markdown, JSON, repo)
├── src/
│   ├── ingest/                     # Moduli onboarding (estrazione, build, preview)
│   ├── utils/                      # Utilità comuni (Drive, GitHub, writer)
├── temp_config/                    # File temporanei config.yaml
├── .env                            # Variabili d'ambiente centralizzate
├── service_account.json            # Credenziali Google API (Drive)
├── requirements.txt                # Dipendenze Python
├── pre_onboarding_readme.md        # Guida pre-onboarding
├── onboarding_pipeline_timmy_kb_v1.2.md # Guida onboarding completo
├── CHANGELOG.md                    # Storico versioni
```

---

## 🛠️ Requisiti tecnici

- **Python >= 3.10**
- **Docker** installato (per preview con Honkit)
- **GitHub CLI (`gh`)** configurato
- **Google Drive API** tramite `service_account.json`

Librerie principali:

```
PyMuPDF, spacy, pydantic, pyyaml, slugify,
google-api-python-client, requests, docker, python-dotenv
```

Installa con:

```bash
pip install -r requirements.txt
```

> ⚠️ **ATTENZIONE:** Non committare mai `.env` o `service_account.json` in repository pubblici!

---

## 🏁 Flusso operativo

### 🔹 Fase 1: Pre-Onboarding

Crea struttura su Drive e file di configurazione:

```bash
py src/pre_onboarding.py
```

Prompt interattivo: slug, nome cliente, conferma caricamento.  
🔎 Dettagli in `pre_onboarding_readme.md`

### 🔹 Fase 2: Onboarding Completo

Esegue l’intera pipeline su cartella già strutturata:

```bash
py src/onboarding_full.py
```

- Lo slug sarà richiesto da input
- Il nome cliente viene caricato da `config.yaml`
- I PDF saranno scaricati ricorsivamente da tutte le sottocartelle di `raw` su Google Drive

🔎 Dettagli in `onboarding_pipeline_timmy_kb_v1.2.md`

---

## 🔄 Step della pipeline

1. Caricamento configurazione (`config_loader.py`)  
2. Download PDF ricorsivo e conversione Markdown (`pdf_to_md.py`)  
3. Estrazione semantica base (`semantic_extractor.py`)  
4. Generazione `README.md` e `SUMMARY.md` (`build_summary.py`)  
5. Preview locale Honkit via Docker (`gitbook_preview.py`)  
6. Deploy GitHub (`github_push.py`)  
7. Pulizia finale (`cleanup.py`)  

> Tutti i path e parametri sono calcolati dinamicamente da `.env` e dalla configurazione cliente.

---

## 🧩 Versione attuale

**v1.2** – Consulta il `CHANGELOG.md` per il log completo delle modifiche.

---

## 🚦 Portabilità & Logging

- Tutti i path e parametri sono centralizzati in `.env` (cross-platform)
- Logging unificato tramite `logging` di Python
- Compatibile e testato su Windows, Mac e Linux

---

## ⚡ Evoluzioni possibili

- Download e parsing automatico di altri formati (docx, immagini, ecc.)
- Pipeline CI/CD e logging avanzato
- Integrazione AI document search / Q&A
