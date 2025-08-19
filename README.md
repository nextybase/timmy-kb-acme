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

### A) Pre-onboarding (setup) — *flusso interattivo di base*

Per avviare la preparazione dell’ambiente cliente esegui:

```bash
py src/pre_onboarding.py
```

**Sequenza tipica**

1. **Slug cliente** → viene richiesto lo *slug* (es. `acme`). Se non valido, il sistema spiega il motivo e chiede un nuovo valore.
2. **Creazione struttura locale** → conferma la generazione delle cartelle `raw/`, `book/`, `config/`, `logs/` e del file `config.yaml` (con backup `.bak` se già presente).
3. **Google Drive (opzionale)**

   * Se le variabili sono configurate: mostra l’ID e chiede se creare/aggiornare la struttura su Drive.
   * Se le credenziali mancano: chiede se proseguire senza Drive.
4. **Riepilogo finale** → stampa le azioni eseguite e indica dove trovare i file.

> Nota: in questa fase non ci sono né anteprima né push. Serve solo a predisporre l’ambiente locale e, se richiesto, quello su Drive.

---

### B) Onboarding completo — *flusso interattivo di base*

Per completare l’onboarding esegui:

```bash
py src/onboarding_full.py
```

**Sequenza tipica**

1. **Slug cliente** → viene richiesto lo *slug*, con validazione e richiesta di reinserimento se necessario.
2. **Conversione PDF → Markdown** → avvio automatico con log di avanzamento; genera `SUMMARY.md` e `README.md` sotto `book/`.
3. **Anteprima HonKit (Docker)**

   * Se Docker è disponibile: *«Avviare l’anteprima ora?»* (default **Sì**). Parte in modalità *detached*, non blocca la pipeline e viene fermata automaticamente al termine.
   * Se Docker non è disponibile: *«Proseguire senza anteprima?»* (default **No**). Se confermi, la pipeline continua senza preview.
4. **Pubblicazione su GitHub (opzionale)**

   * *«Eseguire il push su GitHub?»* (default **No**). Se accetti, controlla `GITHUB_TOKEN` e propone il branch di default (`GIT_DEFAULT_BRANCH`, fallback `main`), che puoi confermare o modificare.
5. **Pulizia finale**

   * *«Eseguire il cleanup?»* (default **Sì**). Rimuove file temporanei e backup, verificando che la preview non sia più attiva. Se lo fosse ancora, propone la chiusura forzata.

**Dettagli tecnici anteprima**

* Porta: `4000` (modificabile via prompt o `--port 4000`).
* Nome container: `honkit_preview_<slug>`.

---

## 4) Comandi rapidi

### Flusso consigliato (interattivo)

```bash
# 1) Setup cliente
py src/pre_onboarding.py

# 2) Onboarding completo (conversione, anteprima, push opzionale, cleanup)
py src/onboarding_full.py
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
Questo progetto è rilasciato sotto i termini della GNU General Public License v3.0 (GPL-3.0).  
Per maggiori dettagli consulta il file [LICENSE](LICENSE.md).

