# 📦 CHANGELOG – OnBoarding NeXT

## v1.0 – Baseline iniziale (luglio 2025)

Questa versione rappresenta il primo consolidamento completo della pipeline di onboarding NeXT. È da considerarsi il **punto zero ufficiale** da cui partirà il versionamento semantico.

---

### 🚀 Principali novità

- ✅ **Integrazione completa** delle fasi **Pre-Onboarding** e **Onboarding**
- 📁 **Struttura unica e coerente** delle cartelle di progetto, moduli Python e file di configurazione
- 🔧 **Funzionalità consolidate**:
  - Generazione cartelle cliente su Google Drive da `cartelle_raw.yaml`
  - Creazione e validazione manuale del file `config.yaml`
  - Parsing semantico dei PDF (Markdown + JSON)
  - Generazione automatica di `README.md` e `SUMMARY.md`
  - Preview GitBook via Docker (`localhost:4000`)
  - Deploy GitHub automatico da template via CLI
  - Pulizia rollback (`temp_config/`) e cleanup completo

---

### 📄 Documentazione allegata

Due documenti nella root descrivono in dettaglio le due fasi operative:

- [`pre_onboarding_readme.md`](./pre_onboarding_readme.md): guida completa alla creazione iniziale della struttura cliente
- [`onboarding_readme.md`](./onboarding_readme.md): guida alla pipeline completa di parsing e pubblicazione

---

### 🧩 Tecnologie e dipendenze

- `Python >= 3.10`
- Librerie: `PyMuPDF`, `spacy`, `pydantic`, `pyyaml`, `python-slugify`, `google-api-python-client`, `docker`, `requests`
- Requisiti extra:
  - Docker installato per preview GitBook
  - GitHub CLI (`gh`) configurato
  - Chiave `service_account.json` per accesso Google Drive

---

### ⚠️ Nota importante

Questa versione **sostituisce completamente la versione precedente del repository online**. Eventuali file o struttura già presenti sono da considerarsi **obsoleti** e saranno sovrascritti con questa baseline v1.0.

---