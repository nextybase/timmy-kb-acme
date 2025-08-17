# Guida Utente – Timmy‑KB (v1.0.3)

Questa guida ti accompagna nell'uso operativo della pipeline Timmy‑KB. È allineata al comportamento degli orchestratori aggiornati (preview Docker coerente, slug posizionale “soft”, alias deprecati `--skip-*`).

---

## Prerequisiti
- **Python ≥ 3.10**
- **Git**
- **Docker** (solo per l’anteprima HonKit; opzionale)
- **Google Drive (Shared Drive)** con **Service Account JSON** (condividi lo *Shared Drive* con l’email del SA)
- (Opzionale) **GitHub token (PAT)** per abilitare il push

### Variabili d’ambiente (essenziale)
| Nome | Descrizione | Esempio |
|---|---|---|
| `GIT_DEFAULT_BRANCH` | Branch di default per checkout/push | `main` |
| `GITHUB_TOKEN` | PAT per il push su GitHub | `ghp_xxx` |
| `DRIVE_ID` | ID dello *Shared Drive* sorgente | `0A...` |
| `DRIVE_PARENT_FOLDER_ID` | (Opz.) Cartella padre alternativa su Drive | `1B...` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path al JSON del Service Account | `./.secrets/sa.json` |

> Non committare `.env` o credenziali nel repo.

---

## Installazione rapida
```bash
git clone https://github.com/nextybase/timmy-kb-acme.git
cd timmy-kb-acme

python -m venv .venv
# macOS/Linux/WSL
source .venv/bin/activate
# Windows (PowerShell)
# .\.venv\Scripts\Activate

pip install -r requirements.txt
```

---

## Flusso standard in 2 step
### 1) Pre‑onboarding (crea struttura cliente + config)
- Genera `output/timmy-kb-<slug>/{raw,book,config,logs}`
- Crea/aggiorna `config.yaml`
- (Se non `--dry-run`) prepara la struttura su Drive e carica `config.yaml`

**Esecuzione**
```bash
# Interattivo: chiede slug e nome cliente
py src/pre_onboarding.py

# Non‑interattivo / CI
py src/pre_onboarding.py --slug acme-srl --name "ACME S.r.l." --non-interactive [--dry-run]
```

> **Slug posizionale “soft”**: puoi passarlo come primo argomento o con `--slug`. In interattivo, se assente, viene richiesto.

---

### 2) Onboarding completo (download → conversione → preview → push)
- Scarica i PDF da Drive (se abilitato)
- Converte in Markdown strutturato e genera `README.md`/`SUMMARY.md`
- Avvia anteprima **HonKit** in Docker (se disponibile o accettata l’assenza)
- Esegue (opz.) il **push** su GitHub

**Esecuzione**
```bash
# Interattivo
py src/onboarding_full.py

# Non‑interattivo / CI
py src/onboarding_full.py --slug acme-srl [--dry-run] [--no-drive] [--push|--no-push] [--port 4000]
```

> **Preview Docker**
> - In **non‑interattivo**: se Docker non è disponibile, la preview viene **saltata automaticamente**.
> - In **interattivo**: se Docker non è disponibile, viene chiesto se **proseguire senza anteprima**.

> **Push**
> - In **interattivo**: viene chiesto se eseguire il push (default **NO**).
> - In **non‑interattivo**: il push è **disabilitato** a meno che passi `--push`.
> - Se `GITHUB_TOKEN` manca, il push fallisce con errore: imposta la variabile o usa `--no-push`.

> **Alias deprecati**: `--skip-drive` e `--skip-push` sono accettati con **warning**. Usa `--no-drive` e `--no-push`.

---

## Output atteso
Struttura in `output/timmy-kb-<slug>/`:
- **book/** → Markdown generati (`*.md`), inclusi `README.md` e `SUMMARY.md`
- **raw/** → PDF scaricati da Drive o caricati manualmente
- **config/** → `config.yaml` (con backup)
- **logs/** → file di log unificato `onboarding.log`

---

## Esempi pratici
**Dry‑run locale senza Drive né push**
```bash
py src/pre_onboarding.py --slug demo --name "Demo" --non-interactive --dry-run
py src/onboarding_full.py --slug demo --no-drive --no-push
```

**Flusso completo con Drive e anteprima (Docker attivo)**
```bash
py src/pre_onboarding.py
# carica PDF in RAW su Drive
py src/onboarding_full.py --slug demo
# se richiesto: conferma preview/push
```

**Batch non‑interattivo con push esplicito**
```bash
export GITHUB_TOKEN=ghp_xxx
py src/onboarding_full.py --slug demo --no-drive --push --non-interactive
```

---

## Troubleshooting
- **Docker non in esecuzione** → Avvia Docker Desktop/daemon. In non‑interattivo la preview viene **saltata**; in interattivo puoi scegliere se proseguire.
- **`GITHUB_TOKEN` mancante** → imposta la variabile o usa `--no-push`.
- **Permessi Google Drive** → verifica `DRIVE_ID` e che lo *Shared Drive* sia condiviso con l’**email del Service Account**.
- **Nessun `.md` generato** → controlla che ci siano PDF in `raw/` (o che il download da Drive sia avvenuto).
- **Slug mancante in non‑interattivo** → passalo come posizionale o `--slug` (altrimenti `ConfigError`).

---

## Exit Codes (deterministici)
| Codice | Eccezione |
|---:|---|
| 0 | Successo |
| 1 | `PipelineError` |
| 2 | `ConfigError` |
| 3 | `PreOnboardingValidationError` |
| 10 | `ConversionError` |
| 21 | `DriveDownloadError` |
| 22 | `DriveUploadError` |
| 30 | `PreviewError` |
| 40 | `PushError` |
| 50 | `CleanupError` |
| 60 | `EnrichmentError` |
| 61 | `SemanticMappingError` |
| 130 | Interruzione utente (`CTRL+C`) |

---

## Note di versione (v1.0.3)
- **Anteprima coerente**: auto‑skip in non‑interattivo; prompt in interattivo.
- **Slug CLI “soft”**: supporto posizionale o `--slug` con richiesta a prompt se assente in interattivo.
- **Nessun cambio di flusso**: release di consolidamento, retro‑compatibile con v1.0.2.
