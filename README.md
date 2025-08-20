# Timmy‑KB — README (v1.0.5 Stable)

Pipeline per la generazione di una **Knowledge Base Markdown AI‑ready** da PDF cliente, con anteprima HonKit (Docker) e push opzionale su GitHub.

---

## Prerequisiti

- **Python ≥ 3.10**
- **Docker** (solo per l’anteprima)
- **Credenziali Google** (Service Account JSON) per Google Drive
- (Opz.) **GitHub Token** (`GITHUB_TOKEN`) per il push

### Variabili d’ambiente

- `SERVICE_ACCOUNT_FILE` / `GOOGLE_APPLICATION_CREDENTIALS` → path al JSON del Service Account
- `DRIVE_ID` / `DRIVE_PARENT_FOLDER_ID` → radice/parent dello spazio Drive
- `GITHUB_TOKEN` → richiesto per il push GitHub
- `GIT_DEFAULT_BRANCH` → branch di default (fallback `main`)
- `YAML_STRUCTURE_FILE` → opzionale override del file YAML per il pre‑onboarding (default `config/cartelle_raw.yaml`)

---

## Struttura output per cliente

```
output/timmy-kb-<slug>/
  ├─ raw/        # PDF scaricati (opzionale)
  ├─ book/       # Markdown + SUMMARY.md + README.md
  ├─ config/     # config.yaml, mapping semantico
  └─ logs/       # onboarding.log (logger unico)
```

---

## Flussi operativi

### Pre‑onboarding

```bash
py src/pre_onboarding.py [--slug <id>] [--name <nome descrittivo>] [--non-interactive] [--dry-run]
```

1. Richiesta *slug* (id cliente).  
2. Creazione struttura locale (`raw/`, `book/`, `config/`, `logs/`).  
3. Drive (opzionale): se configurato crea/aggiorna la struttura remota.  
4. Riepilogo finale delle azioni eseguite.

> Senza credenziali Drive l’esecuzione fallisce, salvo uso di `--dry-run` o `--no-drive`.

---

### Onboarding completo

```bash
py src/onboarding_full.py [--slug <id>] [opzioni]
```

1. Conversione PDF → Markdown.  
2. Anteprima HonKit (Docker), *detached* con stop automatico.  
3. Push GitHub opzionale.  
4. Cleanup finale.

**Opzioni CLI aggiuntive:**
- `--force-push` → forza il push (usa `--force-with-lease`).
- `--force-ack` → aggiunge trailer etico *Force‑Ack* al commit.
- `--allow-offline-env` → bypass variabili mancanti (es. CI senza Drive/GitHub).
- `--docker-retries N` → numero retry su avvio Docker.

---

## Log e sicurezza

- Log centralizzati in `logs/onboarding.log`.
- Mascheramento segreti automatico (`LOG_REDACTION`).
- Scritture atomiche, `is_safe_subpath` per validazione path.

---

## Exit codes principali

- `0` → OK
- `2` → ConfigError (variabili mancanti, slug invalido in batch)
- `30` → PreviewError
- `40` → PushError

---

## Note

- La preview funziona solo se Docker è installato.  
- In batch, senza Docker → viene saltata.  
- In interattivo puoi decidere se continuare senza anteprima.  
- Pubblicazione su GitHub: solo `.md` in `book/`. 

---

