# Timmy-KB – Pipeline per la Knowledge Base di Onboarding NeXT

## 📌 Descrizione
**Timmy-KB** è una pipeline **modulare** che parte dai documenti del cliente (oggi PDF) e produce **Markdown “AI‑ready”** con `README.md` e `SUMMARY.md` pronti per GitBook/Honkit. Include preview **Honkit in Docker** e (opzionalmente) **push su GitHub**.

## 🛠 Requisiti
- **Python ≥ 3.10**
- **Docker** (solo per anteprima Honkit, opzionale ma consigliato)
- **Git** e **GitHub token (PAT)** se abiliti il push
- **Google Drive (Shared Drive)** con **Service Account JSON** (condividi lo *Shared Drive* con l’email del Service Account)
- Dipendenze in `requirements.txt`

## 📂 Struttura (essenziale)
```
root/
 ├─ src/
 │   ├─ pre_onboarding.py      # orchestratore fase 0
 │   ├─ onboarding_full.py     # orchestratore completo
 │   └─ pipeline/              # moduli richiamati dagli orchestratori
 ├─ config/                    # YAML di configurazione e mapping
 ├─ output/                    # output per cliente (md, summary, readme, config, logs)
 └─ docs/                      # guide e policy
```

## ⚙️ Configurazione rapida
1. Crea `.env` con le variabili necessarie (es. `GITHUB_TOKEN`, `DRIVE_ID` / `DRIVE_PARENT_FOLDER_ID`, ecc.).  
2. Prepara il **Service Account JSON** di Google e **condividi** lo *Shared Drive* con la sua **email**. Imposta `DRIVE_ID` nel `.env`.

## 🚀 Installazione
```bash
# Clona il repository
git clone https://github.com/nextybase/timmy-kb-acme.git
cd timmy-kb-acme

# Crea ambiente e installa dipendenze
python -m venv .venv
# macOS/Linux/WSL
source .venv/bin/activate
# Windows (PowerShell)
# .\.venv\Scripts\Activate
pip install -r requirements.txt
```

## ▶️ Flusso tipico in 2 step
### 1) Pre-onboarding (crea struttura cliente e config)
Prepara `output/timmy-kb-<slug>/{raw,book,config,logs}`, genera/aggiorna `config.yaml` e la struttura remota su Drive (se non in `--dry-run`).  
**Interattivo**
```bash
py src/pre_onboarding.py
```
In modalità interattiva ti vengono richiesti **slug** e **nome cliente**.  
**Non‑interattivo / CI**
```bash
py src/pre_onboarding.py --slug acme-srl --name "ACME S.r.l." --non-interactive [--dry-run]
```

### 2) Onboarding completo (download → conversione → preview → push)
Scarica i PDF dallo *Shared Drive* (se abilitato), converte in Markdown, genera `README.md`/`SUMMARY.md`, avvia la preview **Honkit** in Docker e, su conferma, effettua il **push su GitHub**.  
**Interattivo**
```bash
py src/onboarding_full.py
```
**Non‑interattivo / CI**
```bash
py src/onboarding_full.py --slug acme-srl [--dry-run] [--no-drive] [--push|--no-push]
```

> **Nota Preview Docker**  
> - In **modalità non‑interattiva**: se Docker non è disponibile, la preview viene **saltata automaticamente**.  
> - In **modalità interattiva**: se Docker non è disponibile ti viene chiesto se **continuare senza anteprima**.

> **Alias deprecati**  
> `--skip-drive`, `--skip-push` sono **deprecati** (ancora accettati con warning). Usa `--no-drive`, `--no-push`.

## 🔧 Opzioni più usate
- `--slug <slug>`: richiesto in **non‑interattivo** (in interattivo può essere richiesto a prompt)
- `--dry-run`: esecuzione locale senza chiamate ai servizi remoti
- `--no-drive`: usa i PDF **già presenti** in `output/timmy-kb-<slug>/raw/`
- `--push` / `--no-push`: forza o inibisce il push (se omesso: domanda in interattivo, **false** in non‑interattivo)
- `--port <4000>`: porta locale per la preview Honkit

## 📦 Output
Al termine trovi in `output/timmy-kb-<slug>/`:
- cartella **book/** con i Markdown generati (`*.md`), incluso `README.md` e `SUMMARY.md`,
- cartella **raw/** con i PDF scaricati o caricati manualmente,
- cartella **config/** con `config.yaml` (e backup),
- cartella **logs/** con un **unico file** di log consolidato.

## 🧪 Exit Codes (deterministici)
| Codice | Eccezione                              |
|-------:|----------------------------------------|
| 0      | Successo                               |
| 1      | `PipelineError`                        |
| 2      | `ConfigError`                          |
| 3      | `PreOnboardingValidationError`         |
| 10     | `ConversionError`                      |
| 21     | `DriveDownloadError`                   |
| 22     | `DriveUploadError`                     |
| 30     | `PreviewError`                         |
| 40     | `PushError`                            |
| 50     | `CleanupError`                         |
| 60     | `EnrichmentError`                      |
| 61     | `SemanticMappingError`                 |
| 130    | Interruzione utente (`CTRL+C`)         |

## 🛟 Troubleshooting
- **Docker non in esecuzione** → Avvia Docker Desktop/daemon. In **non‑interattivo** la preview viene **saltata** automaticamente.  
- **`GITHUB_TOKEN` mancante** → il push viene **saltato**. Imposta la variabile d’ambiente o esegui il push manuale.  
- **Permessi Google Drive (Shared Drive)** → verifica `DRIVE_ID` e condividi lo *Shared Drive* con l’**email del Service Account** presente nel JSON.  
- **`ModuleNotFoundError` / path errati** → esegui dalla **root** del progetto e assicurati che `.venv` sia attivo.

## 📚 Documentazione
- **Indice**: `docs/index.md`  
- **Guida Utente**: `docs/user_guide.md`  
- **Guida Sviluppatore**: `docs/developer_guide.md`  
- **Regole di Codifica**: `docs/coding_rule.md`  
- **Architettura**: `docs/architecture.md`

## 📜 Licenza
Distribuito sotto licenza **MIT** (vedi `LICENSE`).

---
**Autori**: NeXT Dev Team
