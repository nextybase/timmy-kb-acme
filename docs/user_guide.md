# Guida Utente – Timmy‑KB

Questa guida ti accompagna passo‑passo nell’uso di **Timmy‑KB**, dalla configurazione iniziale all’esecuzione della pipeline, con focus su modalità **interattiva** (default) e varianti **test/CI**.

---

## 📋 Prerequisiti

- **Python ≥ 3.10**
- **Git** installato
- **pip** (oppure **Poetry**) per le dipendenze
- **Docker** attivo per la **preview Honkit** (opzionale ma consigliato)
- Accesso al **repository GitHub**
- File `.env` con le variabili necessarie (es. `DRIVE_ID`, `GITHUB_TOKEN`, …)
- **Google Drive (Shared Drive)** + **Service Account (JSON)**: usa un *Drive Condiviso* e **condividilo** con l’**email** del Service Account indicata nel JSON

---

## ⚡ Installazione

1. **Clona il repository**
   ```bash
   git clone https://github.com/nextybase/timmy-kb-acme.git
   cd timmy-kb-acme
   ```
2. **Crea l’ambiente virtuale e attivalo**  
   *(vedi sezione dedicata sotto per tutti i sistemi)*
   ```bash
   python -m venv .venv
   # Attiva su macOS/Linux/WSL
   source .venv/bin/activate
   ```
   > Su Windows vedi i comandi specifici in **Ambiente virtuale**.
3. **Installa le dipendenze**
   ```bash
   pip install -r requirements.txt
   # In alternativa
   # poetry install
   ```
4. **Configura le variabili**
   - Crea `.env` nella root (es.: `DRIVE_ID`, `GITHUB_TOKEN`, altre variabili richieste dal tuo setup)
   - Verifica i file YAML in `config/` (in particolare `cartelle_raw.yaml`, mapping e template)

---

## 🧰 Ambiente virtuale (Windows/macOS/Linux)

> Consigliato usare `.venv` nella root del repo.

### Creazione
```bash
python -m venv .venv
```

### Attivazione
- **Windows – PowerShell**
  ```powershell
  .\.venv\Scripts\Activate
  ```
- **Windows – CMD**
  ```bat
  .\venv\Scripts\activate.bat
  ```
- **Git Bash / WSL / macOS / Linux**
  ```bash
  source .venv/bin/activate
  ```

> Se PowerShell blocca l’esecuzione:
> ```powershell
> Set-ExecutionPolicy -Scope Process RemoteSigned
> ```

### Installazione dipendenze
```bash
pip install -r requirements.txt
```

### Disattivazione
```bash
deactivate
```

---

## ▶️ Esecuzione della pipeline (interattiva, in due fasi)

La pipeline si esegue tipicamente in **due fasi**: `pre_onboarding` e `onboarding_full`, entrambe **interattive** di default.

### 1) Pre‑onboarding (crea struttura cliente e config)
Prepara l’ambiente locale/Drive, genera `config.yaml` e aggiorna i riferimenti.
```bash
py src/pre_onboarding.py
```
Durante questa fase ti verrà chiesto di inserire:
- lo **slug** del cliente;
- il **nome reale del cliente**.

### 2) Popolamento Google Drive (Shared Drive)
> **Prima di procedere**
>
> Prima di eseguire l’onboarding completo, assicurati che i PDF siano nella cartella **RAW** dello Shared Drive configurato (`DRIVE_ID/<slug>/RAW/`).  
> La gerarchia di sottocartelle è **generata automaticamente** in base a `config/cartelle_raw.yaml` e organizza i documenti per tema (manuali, schede tecniche, presentazioni, ecc.), ottimizzando il parsing semantico e l’analisi.  
> I file presenti in **RAW/** costituiranno la base della knowledge base.

### 3) Onboarding completo (download → conversione → preview → push)
Esegue l’intero flusso: scarica i PDF (se abilitato), converte in Markdown, genera `README.md`/`SUMMARY.md`, avvia la **preview Docker/Honkit** e propone il **push su GitHub**.
```bash
py src/onboarding_full.py
```
Durante l’esecuzione interattiva:
1. Elabora i documenti caricati applicando **arricchimento semantico** (estrazione keyword, tagging tematico, normalizzazioni).
2. Genera la **KB in anteprima** con frontmatter, link coerenti e navigazione.
3. Avvia una **Preview Docker** (Honkit). Se Docker non è attivo, verrà segnalato: avvialo o esegui in modalità che salta la preview.
4. Alla fine della revisione, **premi INVIO** per confermare.
5. Ti verrà chiesto se procedere con il **push su GitHub**:
   - Se confermi, pubblica sul branch configurato.
   - Se rifiuti, la pipeline termina lasciando i file generati in locale.

---

## 🧪 Varianti non interattive (test/CI)

Usa le opzioni CLI per esecuzioni **senza prompt** (es. automazioni CI):

- **Pre‑onboarding**
  ```bash
  py src/pre_onboarding.py --slug acme-srl --name "ACME S.r.l." --non-interactive [--dry-run]
  ```
- **Onboarding completo**
  ```bash
  py src/onboarding_full.py --slug acme-srl [--dry-run] [--no-drive]
  ```
  - `--no-drive` usa i PDF **locali** già presenti in `output/timmy-kb-<slug>/raw/`

> Nota: in modalità non interattiva non vengono richieste conferme (preview/push). Configura le variabili in `.env` e i percorsi prima dell’esecuzione.

---

## 📂 Output finale

Al termine, troverai in `output/`:
- **Markdown arricchiti** (`*.md`) con frontmatter, keyword/tag e metadati;
- **`README.md` e `SUMMARY.md`** coerenti con la struttura generata;
- **File YAML** (configurazioni/mappature aggiornate ove previsto);
- **Log strutturato** dell’esecuzione (unico file di log configurato dagli orchestratori).

---

## 🛟 Troubleshooting

- **Docker non in esecuzione** → Avvia Docker Desktop/daemon prima della preview; in alternativa, esegui in modalità che salta la preview o usa la variante non interattiva.
- **`GITHUB_TOKEN` mancante** → Il push viene **saltato**. Imposta la variabile d’ambiente o effettua il push manuale.
- **Permessi Google Drive (Shared Drive)** → Verifica `DRIVE_ID` e che il **Service Account** (email nel JSON) abbia accesso al **Drive Condiviso**.
- **`ModuleNotFoundError` / path errati** → Esegui i comandi **dalla root** del progetto e assicurati che l’ambiente `.venv` sia attivo.
- **Windows PowerShell** → Se l’attivazione `.venv` fallisce, usa `Set-ExecutionPolicy -Scope Process RemoteSigned` e riprova.

---

## 📚 Risorse utili

- [Guida sviluppatore](developer_guide.md)
- [Regole di codifica](coding_rule.md)
- [Architettura tecnica](architecture.md)

