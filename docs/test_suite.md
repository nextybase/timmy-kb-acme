# Suite di test e utente dummy (v1.9.6)

Questa suite verifica che la pipeline Timmy KB funzioni end-to-end (pre -> tag -> semantic -> full) e a livello di singoli orchestratori. Per velocità e riproducibilità usiamo un utente dummy: una sandbox locale con PDF finti e struttura pronta.

## Prima di tutto: genera il dummy

```powershell
py src/tools/gen_dummy_kb.py --slug dummy
```

Popola `raw/` con PDF sintetici e genera gli artefatti minimi (es. `tags_raw.csv`).

---

## 1) Smoke end-to-end con dummy (locale, senza Drive/push)

```powershell
# Pulizia (opzionale)
Remove-Item -Recurse -Force .\output\timmy-kb-dummy -ErrorAction SilentlyContinue

# 1) Setup locale
py src/pre_onboarding.py --slug dummy --name "Cliente Dummy" --non-interactive --dry-run

# 2) Contenuti finti (PDF + CSV)
py src/tools/gen_dummy_kb.py --slug dummy

# 3) Tagging (locale, auto-proceed)
py src/tag_onboarding.py --slug dummy --source local --non-interactive --proceed

# 4) Conversione + enrichment (no preview)
Esempio headless via `semantic.api` (vedi README) per conversione ed enrichment.

# 5) Push (richiede GITHUB_TOKEN) — opzionale
# $env:GITHUB_TOKEN="<token>"; py src/onboarding_full.py --slug dummy --non-interactive
```

---

## 2) Test con Drive (verifica default Drive di tag_onboarding)

```powershell
# Prerequisiti: Service Account e Drive ID
$env:SERVICE_ACCOUNT_FILE="C:\path\to\sa.json"
$env:DRIVE_ID="xxxxxxxxxxxxxxxxx"

# 1) Setup (NON dry-run per creare struttura su Drive)
py src/pre_onboarding.py --slug demo --name "Cliente Demo" --non-interactive

# 2) Tagging: DEFAULT = drive (nessun --source)
py src/tag_onboarding.py --slug demo --non-interactive --proceed

# 3) Semantic (senza preview)
Esempio headless via `semantic.api` (vedi README) per conversione ed enrichment.

# 4) Push (se vuoi testarlo)
# $env:GITHUB_TOKEN="<token>"; py src/onboarding_full.py --slug demo --non-interactive
```

Nota: se vuoi usare Drive anche nello smoke dummy, carica qualche PDF real-world nella cartella RAW su Drive del cliente `demo` prima del punto 2.

---

## 3) Esecuzione singolo orchestratore (quick)

```powershell
# pre-onboarding solo locale
py src/pre_onboarding.py --slug prova --name "Cliente Prova" --non-interactive --dry-run

# tag-onboarding locale
py src/tag_onboarding.py --slug prova --source local --non-interactive --proceed

# semantic (no preview)
Esempio headless via `semantic.api` (vedi README) per conversione ed enrichment.

# onboarding full (push) — richiede GITHUB_TOKEN
# $env:GITHUB_TOKEN="<token>"; py src/onboarding_full.py --slug prova --non-interactive
```

---

## 4) Calibrazione retriever (locale)

Prerequisiti:
- Workspace gia' popolato (es. `py src/tools/gen_dummy_kb.py --slug dummy`).
- File JSONL di query con righe `{"text": "...", "k": 5}` (vedi `tests/data/retriever_queries.jsonl`).

Esecuzione suggerita:

```powershell
py src/tools/retriever_calibrate.py --slug dummy --scope book --queries tests/data/retriever_queries.jsonl --limits 500:2500:500 --repetitions 3 --dump-top output/timmy-kb-dummy/logs/calibrazione.jsonl
```

Parametri principali:
- `--limits`: elenco separato da virgole oppure range `start:stop:step` per provare piu' `candidate_limit`.
- `--repetitions`: quante volte ripetere ogni coppia query/limite per stabilizzare la misura.
- `--dump-top`: opzionale; salva un JSONL con i doc top-k usando `safe_write_text` dopo la guardia `ensure_within_and_resolve`.

Osservabilita' attesa:
- `retriever_calibrate.start` all'avvio con slug, scope, limiti e ripetizioni.
- Uno o piu' `retriever.raw_candidates` emessi da `retrieve_candidates` (nessuna chiamata alla rete).
- `retriever_calibrate.run` per ogni misura con hits e latenza calcolata.
- `retriever_calibrate.done` (o `retriever_calibrate.no_runs` se nulla da misurare).

Il tool sfrutta `retrieve_candidates` e il DB SQLite locale, quindi e' deterministico: puoi confrontare i risultati per scegliere il `candidate_limit` da applicare con `with_config_candidate_limit` o `with_config_or_budget`.

## 5) Pytest - guida completa

Suggerito:

```powershell
# dal venv attivo
make test
# senza attivare il venv, usa ./venv
make test-vscode
```

Esegue l'intera suite locale. Per default (vedi `pytest.ini`) sono esclusi i test marcati `push` e `drive`.

```powershell
# tutto (locale)
pytest -ra

# includere i test push
pytest -ra -m "push"

# includere i test drive
pytest -ra -m "drive"
```

Consiglio: in CI mantieni il default (no push/drive); in ambienti controllati abilita i marker quando hai le credenziali.

### Elenco dei file di test e come lanciarli

1. `tests/conftest.py`
   Supporto: rende il repo importabile durante i test (aggiunge root e `src/` al `sys.path`). Non si esegue da solo.

2. `tests/test_unit_tags_validator.py`
   Copre il validatore di `tags_reviewed.yaml` (`_validate_tags_reviewed` in `src/tag_onboarding.py`): campi obbligatori, duplicati case-insensitive, caratteri illegali, `merge_into` senza target.

   ```powershell
   # file completo
   pytest tests\test_unit_tags_validator.py -ra
   # singolo test
   pytest tests\test_unit_tags_validator.py::test_validate_ok_minimal -ra
   ```

3. `tests/test_unit_emit_tags_csv.py`
   Copre l'emissione CSV (`_emit_tags_csv`): header corretto, percorsi POSIX prefissati `raw/`, scrittura atomica.

   ```powershell
   pytest tests\test_unit_emit_tags_csv.py -ra
   ```

4. `tests/test_smoke_dummy_e2e.py` (slow)
   Smoke end-to-end: `pre -> dummy -> tag (local) -> semantic (no preview)` con assert minimi sui file generati.
   - Prerequisito: genera prima l'utente dummy (`py src/tools/gen_dummy_kb.py --slug <slug>`).

   ```powershell
   # includi i test lenti
   pytest -ra -m "slow"
   # oppure per nome
   pytest -ra -k "dummy_e2e"
   ```

5. (Opzionale) `tests/test_contract_defaults.py`
   Verifica che `tag_onboarding_main` abbia `source` default = `drive`.

   ```powershell
   pytest tests\test_contract_defaults.py -ra
   ```

### Testare una singola funzione

Puoi eseguire un test specifico indicando il node id `file::test_name` oppure filtrare per substring con `-k`.

```powershell
# esecuzione puntuale per node id
pytest tests\test_unit_tags_validator.py::test_validate_missing_keys -ra

# filtro per nome (substring)
pytest -k "book_guard and raises" -ra

# output più dettagliato
pytest -vv -k test_validate_ok_minimal
```

---

## 6) Log e pulizia rapida

```powershell
# ultimi log
Get-Content .\output\timmy-kb-*\logs\*.log -Tail 80

# pulizia sandbox di prova
Get-ChildItem .\output -Directory "timmy-kb-*" | Remove-Item -Recurse -Force
```

---

## Aggiornamenti v1.9.6 (nuovi test)

- `tests/test_file_io_append.py`: simula append concorrente e failure per validare `safe_append_text`.
- `tests/test_retriever_calibrate_io.py`: allineato al wrapper `retrieve_candidates` e verifica logging strutturato.
- Aggiornate le fixture dummy per includere QueryParams completi nel tool di calibrazione.

- `tests/test_vision_ai_module.py`: copre estrazione PDF, conversione JSON->YAML, salvataggio dello snapshot e gli errori
  `ConfigError` sul nuovo pipeline Vision Statement.
- `tests/test_tag_onboarding_drive_guard_main.py`:
  verifica che l'orchestratore `tag_onboarding_main(..., source="drive")` sollevi `ConfigError`
  con messaggio esplicito quando le funzioni Drive non sono disponibili (hint: `pip install .[drive]`).

- `tests/test_ui_drive_services_guards.py`:
  verifica che i servizi UI `emit_readmes_for_raw` e `download_raw_from_drive_with_progress` sollevino `RuntimeError`
  con messaggio comprensibile in assenza degli extra Drive.
