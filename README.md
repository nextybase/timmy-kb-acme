# Timmy‑KB — README (v1.2.0)

Pipeline per la generazione di una **Knowledge Base Markdown AI‑ready** a partire da PDF cliente, con arricchimento semantico, anteprima HonKit (Docker) e push opzionale su GitHub【355†README.md】.

---

## Prerequisiti

- **Python ≥ 3.10**
- **Docker** (solo per l’anteprima)
- (Solo per pre‑onboarding con Drive) **Credenziali Google** (Service Account JSON)
- (Opz.) **GitHub Token** (`GITHUB_TOKEN`) per il push

### Variabili d’ambiente

- `SERVICE_ACCOUNT_FILE` → path al JSON del Service Account (solo per Drive)
- `DRIVE_ID` → radice/parent dello spazio Drive (solo per Drive)
- `GITHUB_TOKEN` → richiesto per il push GitHub
- `GIT_DEFAULT_BRANCH` → branch di default (fallback `main`)
- `YAML_STRUCTURE_FILE` → opzionale override del file YAML per il pre-onboarding (default `config/cartelle_raw.yaml`; fallback `src/config/cartelle_raw.yaml`)
- `LOG_REDACTION` → `auto` (default), `on`, `off`
- `ENV` → `dev`, `prod`, `ci`, ...
- `CI` → `true`/`false`

---

## Struttura output per cliente

```
output/timmy-kb-<slug>/
  ├─ raw/        # PDF caricati/scaricati
  ├─ book/       # Markdown + SUMMARY.md + README.md
  ├─ semantic/   # tags.yaml e altri enrichment
  ├─ config/     # config.yaml aggiornato con ID Drive
  └─ logs/       # log centralizzati (pre_onboarding, tag_onboarding, onboarding_full)
```

> Lo **slug** deve rispettare la regex in `config/config.yaml`. In interattivo, se non valido, viene richiesto di correggerlo.

---

## Flussi operativi

### Modalità interattiva vs CLI

- **Interattiva** → guidata via prompt (slug, nome cliente, conferme preview/push).\
  Esempi:

  ```bash
  py src/pre_onboarding.py
  py src/tag_onboarding.py
  py src/onboarding_full.py
  ```

- **CLI (batch)** → parametri espliciti (`--slug`, `--name`, `--no-preview`, `--no-push`, ecc.), nessun prompt.\
  Esempi:

  ```bash
  py src/pre_onboarding.py --slug acme --name "Cliente ACME" --non-interactive
  py src/tag_onboarding.py --slug acme --non-interactive
  py src/onboarding_full.py --slug acme --no-preview --no-push
  ```

---

### 1) Pre-onboarding

```bash
py src/pre_onboarding.py [--slug <id>] [--name <nome descrittivo>] [--non-interactive] [--dry-run]
```

1. Richiede *slug* (e, se interattivo, nome cliente).
2. Crea struttura locale (`raw/`, `book/`, `config/`, `logs/` e `config.yaml`).
3. Drive opzionale: se configurato crea/aggiorna la struttura remota e carica `config.yaml`.
4. Aggiorna `config.yaml` locale con gli ID Drive.

> In `--dry-run` lavora solo in locale, senza Drive.

---

### 2) Tagging semantico

```bash
py src/tag_onboarding.py --slug <id>
```

1. Legge i PDF in `raw/`.
2. Genera o aggiorna `semantic/tags.yaml` con i tag riconosciuti.
3. Prepara i dati per l’arricchimento frontmatter.

---

### 3) Onboarding completo

```bash
py src/onboarding_full.py [--slug <id>] [opzioni]
```

1. Conversione PDF → Markdown in `book/`.
2. Arricchimento frontmatter dei `.md` usando `semantic/tags.yaml`.
3. Generazione `README.md` e `SUMMARY.md`.
4. Anteprima HonKit (Docker) opzionale.
5. Push GitHub opzionale.

**Opzioni CLI aggiuntive:**

- `--no-preview` → salta la preview Docker.
- `--no-push` → salta il push GitHub.
- `--preview-port <N>` → porta per la preview (default 4000).
- `--stop-preview` → ferma la preview Docker al termine.

---

## Log e sicurezza

- Log centralizzati in `output/timmy-kb-<slug>/logs/`.
- Mascheramento segreti automatico (`LOG_REDACTION`).
- Scritture atomiche, validazione path (`is_safe_subpath`).

---

## Exit codes principali

- `0` → OK
- `2` → ConfigError (slug invalido, variabili mancanti)
- `30` → PreviewError
- `40` → PushError

---

## Note operative

- La **RAW è sempre locale** (`output/timmy-kb-<slug>/raw`); Drive è usato solo per la sincronizzazione iniziale.
- La preview funziona solo se Docker è disponibile; in modalità batch viene saltata.
- In interattivo puoi decidere se avviare/fermare preview e push.
- Pubblicazione su GitHub: vengono inclusi solo i `.md` in `book/`.

---

