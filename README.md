# Timmy-KB – Knowledge Base Pipeline per Onboarding NeXT

## 📌 Descrizione
Timmy-KB è una **pipeline modulare** per creare la Knowledge Base di un cliente a partire dai suoi documenti (oggi PDF). Produce **Markdown semantico** con frontmatter, `README.md` e `SUMMARY.md` pronti per GitBook/Honkit, e può effettuare **push automatico su GitHub**.

## 🛠 Requisiti
- **Python ≥ 3.10**
- **Docker** (solo per anteprima GitBook/Honkit)
- **Git** e (opzionale) **GitHub CLI / token** per il push
- **Google Drive (Shared Drive)** con **Service Account** (JSON): usa un *Drive Condiviso* e **concedi l’accesso al Drive condiviso** all’**email** del Service Account indicata nel file JSON
- Dipendenze dal file `requirements.txt`

## 📂 Struttura (essenziale)
```
root/
 ├─ src/
 │   ├─ pre_onboarding.py      # orchestratore fase 0
 │   ├─ onboarding_full.py     # orchestratore completo
 │   └─ pipeline/              # moduli richiamati dagli orchestratori
 ├─ config/                    # YAML di configurazione e mapping
 ├─ output/                    # output per cliente (md, summary, readme, config)
 └─ docs/                      # guide e policy
```

## ⚙️ Configurazione
1. Crea e compila `.env` con le variabili necessarie (es. `GITHUB_TOKEN`, `DRIVE_ID`, ecc.).
2. Prepara le credenziali Google (file JSON del Service Account) se usi l’integrazione Drive. **Usa uno Shared Drive** e **condividilo con l’email del Service Account**; imposta `DRIVE_ID` del Drive condiviso nel `.env`.

## 🚀 Installazione
```bash
# Clona il repository
git clone https://github.com/nextybase/timmy-kb-acme.git
cd timmy-kb-acme

# Crea ambiente e installa dipendenze
python -m venv .venv && source .venv/bin/activate  # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt
```

## ▶️ Flusso tipico
### 1) Pre-onboarding (crea struttura cliente e config)
Esegue la **fase 0**: crea struttura locale/Drive, genera `config.yaml` e aggiorna i riferimenti.
```bash
py src/pre_onboarding.py
```
_In modalità interattiva verranno richiesti:_ **slug** del cliente e **nome azienda**.

**Modalità test/CI (non interattiva)**
```bash
py src/pre_onboarding.py --slug acme-srl --name "ACME S.r.l." --non-interactive [--dry-run]
```
**Opzioni principali (per modalità non interattiva/test)**
- `--slug` slug del cliente (obbligatorio in modalità non interattiva)
- `--name` nome leggibile del cliente
- `--non-interactive` disabilita prompt CLI
- `--dry-run` crea solo struttura locale, **senza** contattare Drive

### 2) Onboarding completo (download, conversione, anteprima, push)
Scarica i PDF (se abilitato), converte in Markdown, genera `README.md`/`SUMMARY.md`, fa la preview Docker/Honkit e opzionalmente il push su GitHub.
```bash
py src/onboarding_full.py
```
_In modalità interattiva verrà richiesto:_ solo lo **slug** del cliente.

**Modalità test/CI (non interattiva)**
```bash
py src/onboarding_full.py --slug acme-srl [--dry-run] [--no-drive]
```
**Opzioni principali (per modalità non interattiva/test)**
- `--slug` slug del cliente (richiesto in batch)
- `--dry-run` salta download da Drive e si ferma prima della conversione
- `--no-drive` forza l’uso dei PDF locali già presenti in `output/timmy-kb-<slug>/raw/`

> In modalità **interattiva**, gli orchestratori chiedono gli input necessari (_pre_onboarding_: **slug** + **nome**; _onboarding_full_: solo **slug**), propongono la **preview Docker/Honkit** e chiedono conferma per il **push su GitHub**. In modalità **batch** richiedono `--slug` ed eseguono senza input.

## 🧪 Test
```bash
pytest tests/ --maxfail=1 --disable-warnings -q
```

## 🛟 Troubleshooting
- **Docker non in esecuzione** → Avvia Docker Desktop/daemon prima di eseguire l’anteprima; in alternativa esegui in modalità non interattiva o salta la preview.
- **Manca `GITHUB_TOKEN`** → Il push viene saltato. Imposta la variabile ambiente o effettua il push manuale.
- **Permessi Google Drive (Shared Drive)** → Usa un **Drive Condiviso**, imposta `DRIVE_ID` corretto e **condividi il Drive** con l’email del Service Account (quella nel JSON).

## 📚 Documentazione
Consulta l’indice completo: **[docs/index.md](docs/index.md)**

- `docs/user_guide.md` — guida operativa per chi usa la pipeline: setup, prerequisiti, modalità **interattiva** vs **non interattiva**, flusso tipico e troubleshooting.
- `docs/developer_guide.md` — riferimento per sviluppatori: struttura di `src/`, orchestratori, estensioni dei moduli in `pipeline/`, convenzioni e strumenti di sviluppo.
- `docs/coding_rule.md` — regole di codifica e qualità: stile, linting, test, gestione dei log, naming e convenzioni dei commit.
- `docs/architecture.md` — panoramica architetturale: componenti principali, flussi (pre_onboarding → onboarding_full → preview/push), integrazioni (Google Drive, Docker/Honkit, GitHub).

## 📜 Licenza
Distribuito sotto licenza **MIT** (vedi `LICENSE`).

---
**Autori**: NeXT Dev Team

