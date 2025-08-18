# Timmy-KB — Knowledge Base Pipeline (v1.0.4 Stable)

Pipeline modulare per trasformare i PDF del cliente in una **KB Markdown AI‑ready** (GitBook/HonKit), con anteprima Docker opzionale e push opzionale su GitHub.

> Stato: **v1.0.4 Stable**. Documento aggiornato ai micro‑fix di robustezza introdotti in questa sessione; il bump è allineato al CHANGELOG.

---

## TL;DR

1. Pre‑onboarding (setup locale + Drive opzionale)
   ```bash
   py src/pre_onboarding.py --slug acme --non-interactive --dry-run
   ```
2. Onboarding completo (download → conversione → preview → push)
   ```bash
   # senza Drive e senza push (anteprima detached se Docker è disponibile)
   py src/onboarding_full.py --slug acme --no-drive --non-interactive
   ```

---

## Requisiti

- Python ≥ 3.10.
- Docker per la preview HonKit; se assente la preview viene saltata in batch.
- Google Drive API con credenziali Service Account (.json).
- GitHub `GITHUB_TOKEN` solo se si vuole eseguire il push.

### Variabili d’ambiente

- `SERVICE_ACCOUNT_FILE` oppure `GOOGLE_APPLICATION_CREDENTIALS` per le credenziali GCP.
- `DRIVE_ID` oppure `DRIVE_PARENT_FOLDER_ID` come radice per i PDF del cliente.
- `GITHUB_TOKEN` per il push (opzionale).
- `GIT_DEFAULT_BRANCH` come branch di default per il push (fallback `main`).
- `LOG_REDACTION` per abilitare la redazione di log sensibili.

---

## Struttura di output per cliente

```
output/timmy-kb-<slug>/
  ├─ raw/        # PDF scaricati (opzionale)
  ├─ book/       # Markdown generati + SUMMARY.md + README.md
  ├─ config/     # config.yaml, mapping semantico
  └─ logs/       # onboarding.log (logger unico per cliente, rotazione opzionale)
```

---

## Flussi

### 1) Pre‑onboarding

Crea la struttura locale, inizializza o aggiorna `config.yaml` e, se richiesto, prepara la struttura su Drive. Al termine, se non è in `--dry-run`, carica la config su Drive e aggiorna localmente gli ID remoti.

Esempi:

```bash
# setup minimale, senza servizi remoti
py src/pre_onboarding.py --slug acme --non-interactive --dry-run

# setup con Drive (richiede variabili d'ambiente corrette)
py src/pre_onboarding.py --slug acme
```

### 2) Onboarding completo

Converte i PDF in Markdown strutturato, genera `SUMMARY.md` e `README.md`, valida la directory `book/`, avvia la **preview HonKit** (se Docker è disponibile) e, se richiesto, pubblica su GitHub.

Esempi:

```bash
# batch/CI: niente prompt, preview saltata se Docker non c'è, push disabilitato
py src/onboarding_full.py --slug acme --no-drive --non-interactive

# interattivo: se Docker assente chiede se proseguire; chiede conferma per il push
py src/onboarding_full.py --slug acme --no-drive
```

---

## Anteprima (HonKit + Docker)

- L’anteprima è eseguita **in modalità detached** e non blocca il flusso.
- L’orchestratore arresta **automaticamente** il container alla fine dell’esecuzione.
- Se Docker non è disponibile, in `--non-interactive` la preview è **auto‑skip**; in modalità interattiva viene chiesto se proseguire senza anteprima (default **NO**).

Porta e container:

- Porta di default `4000` (override con `--port 4000`).
- Nome container `honkit_preview_<slug>`.

---

## Push su GitHub (opzionale)

- Eseguito da `src/pipeline/github_utils.py`.
- Richiede `GITHUB_TOKEN`.
- Il branch è letto da `GIT_DEFAULT_BRANCH` (fallback `main`).
- In batch il push non avviene a meno di `--push`; in interattivo viene richiesta conferma.
- Pubblica solo i file `.md` sotto `book/` e ignora i backup.
- Dopo il push, l’orchestratore può proporre un cleanup degli artefatti legacy.

Esempio:

```bash
export GITHUB_TOKEN=ghp_xxx
export GIT_DEFAULT_BRANCH=main
py src/onboarding_full.py --slug acme --no-drive --non-interactive --push
```

---

## Regole operative (estratto)

- Orchestratori: UX/CLI, prompt e mapping deterministico eccezioni→EXIT\_CODES.
- Moduli: azioni tecniche, niente `input()` e niente `sys.exit()`.
- Logging: logger strutturati (`onboarding.log`), nessun `print()`, redazione log opzionale.
- Sicurezza I/O: `is_safe_subpath`, scritture atomiche, nessun segreto nei log.
- Slug: validazione via regex da `config/config.yaml` con cache e funzione di clear.
- Alias deprecati: `--skip-drive` e `--skip-push` sono mantenuti come avvisi e rimappati a `--no-drive` e `--no-push`.

---

## Exit codes (estratto)

- `0` esecuzione completata.
- `2` `ConfigError` (per esempio variabili mancanti o slug invalido in batch).
- `21` `DriveDownloadError`.
- `30` `PreviewError`.
- `40` `PushError`.

La mappatura completa è nella documentazione utente.

---

## Tools

Gli strumenti in `src/tools/` sono **standalone e interattivi** (si eseguono da terminale).

- `cleanup_repo.py` per la pulizia sicura degli artefatti locali di uno slug e, se richiesto, l’eliminazione del repository GitHub convenzionale tramite `gh`.

  Uso:

  ```bash
  py src/tools/cleanup_repo.py
  ```

- `gen_dummy_kb.py` per generare una KB di test completa con slug `dummy`, cartelle RAW da `config/cartelle_raw.yaml` e PDF dummy da `config/pdf_dummy.yaml` (fallback `.txt` se `fpdf` non è disponibile).

  Uso:

  ```bash
  py src/tools/gen_dummy_kb.py
  ```

- `refactor_tool.py` come utility con due modalità: Trova e Trova & Sostituisci, con anteprima e backup `.bak`.

  Uso:

  ```bash
  py src/tools/refactor_tool.py
  ```

I log degli strumenti sono strutturati; i path assenti e gli skip non critici sono a livello `DEBUG`.

---

## Troubleshooting

- Docker non installato: la preview è saltata in batch; in interattivo puoi scegliere se proseguire senza anteprima.
- Token GitHub mancante: il push fallisce; imposta `GITHUB_TOKEN` o usa `--no-push`.
- Slug invalido: in batch errore; in interattivo viene richiesto di correggerlo.
- Drive non configurato: in `pre_onboarding` con Drive attivo viene sollevato `ConfigError`.

---

## Licenza

TBD.

