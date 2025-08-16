# Coding Rules – Timmy-KB (docs/coding\_rule.md)

> **Scopo** Queste regole assicurano codice coerente, manutenibile e sicuro per la pipeline Timmy‑KB. Valgono per tutto il repository, con enfasi su orchestratori (`src/pre_onboarding.py`, `src/onboarding_full.py`) e moduli in `src/pipeline/`, `src/semantic/`, `src/tools/`.

---

## 1) Versioni, dipendenze e ambiente

- **Python**: ≥ **3.10**. Evitare feature deprecate o non compatibili.
- **Dipendenze**: dichiarate in `requirements.txt` (pin/upper-bound dove necessario). Evitare dipendenze non essenziali.
- **Ambiente**: usare `python -m venv .venv` e attivazione locale. Niente path hard‑coded; usare variabili d’ambiente e `.env` (mai committare segreti).
- **Compatibilità OS**: usare sempre `pathlib` per i percorsi.

## 2) Struttura del repository (fonte di verità)

```txt
root/
 ├─ src/
 │   ├─ pre_onboarding.py    # orchestratore fase 0 (interattivo di default)
 │   ├─ onboarding_full.py   # orchestratore end‑to‑end (interattivo di default)
 │   ├─ pipeline/            # moduli core (drive, github, utils, logging, eccezioni, costanti, …)
 │   ├─ semantic/            # estrazione/mapping semantico e post‑processing
 │   └─ tools/               # utility CLI, validatori, refactoring
 ├─ config/                  # YAML di configurazione (es. cartelle_raw.yaml, mapping, template)
 ├─ output/                  # output Markdown/YAML per cliente (README.md, SUMMARY.md, *.md)
 ├─ tests/                   # unit + end‑to‑end (pytest)
 └─ docs/                    # documentazione (index.md, user_guide.md, developer_guide.md, coding_rule.md, …)
```

**Nota**: gli **orchestratori sono in **``, non in `src/pipeline/`. `pipeline/` contiene **solo** moduli riusabili.

## 3) Principi architetturali

- **Separation of Concerns**: orchestratori = coordinamento/UX CLI; moduli = logica applicativa; `semantic/` = arricchimento; `tools/` = helper non core.
- **Idempotenza**: ogni step deve poter essere rieseguito senza effetti collaterali inattesi (pulizia temporanei, check esistenza file/cartelle).
- **Fail‑fast, rollback chiaro**: in caso di errore interrompere ordinatamente; rilasciare risorse/handle; ripristinare stato se previsto.
- **Configurazione esterna**: niente costanti di ambiente nel codice; leggere da `.env`/YAML e validare.
- **Assenza di I/O UI nei moduli**: prompt e input utente **solo** negli orchestratori.

## 4) Convenzioni di codice

- **Naming**: `snake_case` per file, funzioni e variabili; `PascalCase` per classi; `UPPER_SNAKE_CASE` per costanti.
- **Type hints**: obbligatorie su tutte le funzioni pubbliche; preferire `typing` moderno (es. `list[str]`).
- **Docstring**: stile **Google** con sezioni `Args`, `Returns`, `Raises`. Un esempio:
  ```py
  def build_summary(nodes: list[str]) -> str:
      """Genera il SUMMARY.md a partire dai titoli.

      Args:
          nodes: Elenco dei titoli in ordine gerarchico.

      Returns:
          Contenuto del file SUMMARY.md.

      Raises:
          ValueError: Se `nodes` è vuoto.
      """
  ```
- **Imports**: assoluti rispetto a `src/`; vietati i print di debug; vietato il wildcard import.
- **Style**: preferire `black` (format), `ruff/flake8` (lint) e `isort` (imports). Nessun commit con lint/format falliti.

## 5) Logging & osservabilità

- **Niente **`` in produzione. Usare `logging` con configurazione centralizzata (**unico file log**, es. `onboarding.log`).
- **Livelli**: `DEBUG` (sviluppo), `INFO` (flusso), `WARNING` (degradazioni), `ERROR` (errori gestiti), `CRITICAL` (errori bloccanti).
- **Formato** (consigliato): `%(asctime)s | %(levelname)s | %(name)s | %(message)s`.
- **Propagazione**: abilitata; i moduli usano `getLogger(__name__)`; l’orchestratore configura handler console+file.
- **Tracciabilità**: ogni step rilevante logga inizio/fine, input principali, path usati, conteggi file trattati.

## 6) Gestione errori

- **Eccezioni dedicate** (in `src/pipeline/exceptions.py`): definire classi per errori di configurazione, I/O, servizi esterni (Drive/GitHub/Docker), validazione.
- **Context‑rich**: non silenziare; wrappare con messaggi esplicativi e `exc_info=True` nel log.
- **UX**: negli orchestratori, messaggi chiari e azionabili (es. "Docker non è attivo: avvialo o esegui senza preview").

## 7) CLI & UX degli orchestratori

- **Modalità di default**: **interattiva** (prompt in chiaro). Richieste:
  - `pre_onboarding.py` → **slug** + **nome azienda**
  - `onboarding_full.py` → **slug**
- **Modalità non interattiva (test/CI)**: parametri espliciti (`--slug`, `--name`, `--non-interactive`, `--dry-run`, `--no-drive`). Nessun prompt.
- **Conferme esplicite**: preview Docker/Honkit e push GitHub chiedono conferma in modalità interattiva.
- **Output user‑facing**: riassumere esito, percorsi generati/aggiornati e prossimi passi.

## 8) Gestione file e percorsi

- **Path**: usare `pathlib` e funzioni helper (no `os.path` legacy se non necessario).
- **Atomicità**: scritture su file con temp + rename per evitare corruzioni.
- **Encoding**: UTF‑8 con gestione robusta dei caratteri speciali.
- **Link Markdown**: preferire **relativi**; evitare assoluti hard‑coded.

## 9) Integrazioni esterne (guard‑rails)

### 9.1 Google Drive (Shared Drive)

- Usare **Shared Drive** identificato da `DRIVE_ID`.
- **Condividere il Drive** con l’**email del Service Account** presente nel JSON.
- Cartella sorgente: `DRIVE_ID/<slug>/RAW/`. Le sottocartelle sono **generate da** `config/cartelle_raw.yaml`.
- Le operazioni Drive devono essere idempotenti (crea‑se‑manca, non duplicare).

### 9.2 Docker/Honkit (preview)

- Verificare che Docker sia attivo prima della preview; messaggio chiaro se non disponibile.
- In CI o modalità non interattiva, consentire **skip** della preview quando appropriato.

### 9.3 GitHub (push)

- Il push è **opzionale**. Richiede `GITHUB_TOKEN` o auth equivalente; se assente, **saltare** con log/avviso.
- Commit con messaggi standard (vedi §12) e branch puliti.

## 10) Generazione contenuti (Markdown, README/SUMMARY)

- Ogni markdown deve avere **titolo** coerente e, se previsto, **frontmatter** minimale.
- `README.md` e `SUMMARY.md` devono essere **sempre aggiornati** coerentemente con l’albero generato.
- I nomi file devono essere stabili e descrittivi (`snake_case`), evitando spazi/caratteri speciali.

## 11) Test e qualità

- **Pytest** per unit ed end‑to‑end. Obiettivi minimi: testare parsing PDF→MD, generazione README/SUMMARY, gestione errori esterni.
- **Fixture**: usare PDF/dataset sintetici in `tests/fixtures/` (nessun dato sensibile).
- **Determinismo**: evitare dipendenze dal tempo; se servono timestamp, mockare.
- **CI**: step di lint, test e (opz.) build preview in container.

## 12) Git, commit e PR

- **Conventional Commits** consigliati: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:` …
- PR piccole e focalizzate; descrivere cosa cambia, perché, e impatto su UX/ops.
- Vietati commit di segreti o file generati; `.gitignore` aggiornato.

## 13) Sicurezza e privacy

- Mai committare token, JSON di Service Account, o `.env` reali. Fornire esempi come `.env.sample`.
- Validare input utente / path per evitare traversal o sovrascritture involontarie.
- Log: non includere dati sensibili (token, identificativi privati); offuscare se necessario.

## 14) Linee guida linguistiche

- **Identificatori e codice**: in **inglese**.
- **Messaggi utente/log user‑facing**: in **italiano** chiaro e operativo.

## 15) Esempi rapidi

```py
# Logging modulare
logger = logging.getLogger(__name__)
logger.info("Creazione struttura RAW completata", extra={"slug": slug, "drive_id": drive_id})

# Gestione errori con contesto
try:
    create_shared_drive_structure(slug)
except DrivePermissionError as e:
    logger.error("Service Account senza accesso allo Shared Drive", exc_info=True)
    raise
```

## 16) Checklist pre‑merge

-

---

**Ultimo aggiornamento**: 2025‑08‑16

