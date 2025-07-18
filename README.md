# 🚀 OnBoarding NeXT – v1.2

Benvenuto nel repository ufficiale del sistema di onboarding per il progetto **NeXT**.  
Questa versione (`v1.2`) introduce controlli di idempotenza, rollback automatici su Drive, e verifiche preventivo-interattive per il deploy GitHub.  

---

## 📚 Documentazione inclusa

- [`pre_onboarding_readme.md`](./pre_onboarding_readme.md)  
  👉 *Creazione struttura cliente su Google Drive e generazione `config.yaml`.*

- [`onboarding_pipeline_timmy_kb_v1.3.md`](./onboarding_pipeline_timmy_kb_v1.3.md)  
  👉 *Pipeline completa: download PDF ricorsivo, preview Docker e deploy GitHub.*

---

## 🧭 Obiettivo del progetto

Offrire una pipeline **robusta**, **automatizzata** e **adattiva** per gestire end-to-end il processo di onboarding dei clienti:

- ✅ Creazione cartelle su Drive con validazione e rollback
- 🔄 Download ricorsivo dei PDF e conversione in Markdown + JSON semantici
- 🧪 Anteprima locale della KB con Honkit (Docker)
- 🚀 Deploy GitHub con check interattivo ed evitamento duplicazioni
- 🧠 Compatibilità nativa con cloni NeXT (Timmy, ClasScrum, Zeno)

---

## 🏁 Flusso operativo

### 🔹 Fase 1: Pre-Onboarding

py src/pre_onboarding.py

Richiede solo slug e nome cliente.  
✔️ Check se cartella esiste già su Drive  
✔️ Validazione struttura YAML e rollback su errore  
🔎 Dettagli in `pre_onboarding_readme.md`

---

### 🔹 Fase 2: Onboarding completo
py src/onboarding_full.py

✔️ Check anticipato se la repo GitHub esiste già  
✔️ Download ricorsivo PDF  
✔️ Generazione Markdown + JSON  
✔️ Preview Docker con Honkit  
✔️ Push GitHub interattivo o fallback

🔎 Dettagli in `onboarding_readme.md`
