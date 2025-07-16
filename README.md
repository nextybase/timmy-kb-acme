# 🚀 OnBoarding NeXT – v1.0

Benvenuto nel repository ufficiale del sistema di onboarding per il progetto **NeXT**. Questa versione rappresenta la **baseline consolidata** delle procedure di pre-onboarding, parsing semantico e pubblicazione della Knowledge Base.

---

## 📚 Documentazione inclusa

Nella root del progetto troverai due documenti fondamentali:

- [`pre_onboarding_readme.md`](./pre_onboarding_readme.md)  
  👉 Guida completa alla fase di creazione iniziale cliente, struttura su Drive, e validazione manuale

- [`onboarding_readme.md`](./onboarding_readme.md)  
  👉 Pipeline automatizzata per conversione PDF → Markdown semantico, preview GitBook, e deploy GitHub

---

## 🧭 Obiettivo del progetto

Costruire una pipeline robusta, automatica e AI-ready per gestire:

- La configurazione iniziale dei clienti (strutture cartelle + `config.yaml`)
- La generazione di contenuti documentali semantici (markdown + json)
- L'integrazione con GitBook, GitHub e Google Drive

---

## 🧱 Struttura generale

```
project-root/
├── config/
├── clienti/
├── output/
├── src/
│   ├── ingest/
│   ├── utils/
├── temp_config/
├── .env
├── service_account.json
├── requirements.txt
├── pre_onboarding_readme.md
├── onboarding_readme.md
├── CHANGELOG.md
```

---

## 🛠️ Requisiti tecnici

- Python >= 3.10
- Docker installato
- GitHub CLI (`gh`)
- Google Drive collegato via `service_account.json`

Installa le dipendenze:

```bash
pip install -r requirements.txt
```

---

## 🏁 Avvio rapido

1. Esegui la fase di pre-onboarding:
   ```bash
   py src/pre_onboarding.py
   ```

2. Esegui la pipeline completa:
   ```bash
   py src/onboarding_full.py <slug_cliente>
   ```

---

## 🧩 Versione attuale

**v1.0** – [vedi changelog](./CHANGELOG.md)

---