# Suite di test e uso dell’utente **dummy**

Questi test servono a verificare rapidamente che la pipeline Timmy‑KB lavori end‑to‑end (pre → tag → semantic → full) o per singoli orchestratori. Per accelerare e rendere riproducibili i test **usiamo un utente dummy**, cioè una sandbox con PDF finti e struttura già pronta.

**Come funziona in sintesi**

- Prima di eseguire i test locali, **crea l’utente dummy con il tool** `py src/tools/gen_dummy_kb.py`: popola `raw/` con PDF sintetici e genera i file minimi (es. `tags_raw.csv`).
- I test end‑to‑end usano questi contenuti per evitare dipendenze esterne (Drive/GitHub), ma puoi anche testare lo scenario con Drive passando le variabili d’ambiente.
- `tag_onboarding` ha **default = Drive**: negli smoke locali usiamo `--source local` perché i PDF dummy sono già in `raw/`.

> **Prima di tutto, crea l’utente dummy**
>
> ```powershell
> py src/tools/gen_dummy_kb.py --slug dummy
> ```
>
> Prepara la sandbox locale e **genera i PDF** e gli altri artefatti per i test.

---

## 1) Smoke end‑to‑end con dummy (locale, senza Drive/push)

```powershell
# pulizia (opzionale)
Remove-Item -Recurse -Force .\output\timmy-kb-dummy -ErrorAction SilentlyContinue

# 1) setup locale
py src/pre_onboarding.py --slug dummy --name "Cliente Dummy" --non-interactive --dry-run

# 2) contenuti finti (PDF + CSV)
py src/tools/gen_dummy_kb.py --slug dummy

# 3) tagging (locale, auto-proceed)
py src/tag_onboarding.py --slug dummy --source local --non-interactive --proceed

# 4) conversione + enrichment (no preview)
py src/semantic_onboarding.py --slug dummy --no-preview --non-interactive

# 5) push (richiede GITHUB_TOKEN) — opzionale
# $env:GITHUB_TOKEN="<token>"; py src/onboarding_full.py --slug dummy --non-interactive
```

---

## 2) Test con Drive (verifica default Drive di `tag_onboarding`)

```powershell
# prerequisiti: Service Account e Drive ID
$env:SERVICE_ACCOUNT_FILE="C:\path\to\sa.json"
$env:DRIVE_ID="xxxxxxxxxxxxxxxxx"

# 1) setup (NON dry-run per creare struttura su Drive)
py src/pre_onboarding.py --slug demo --name "Cliente Demo" --non-interactive

# 2) tagging: DEFAULT = drive (nessun --source)
py src/tag_onboarding.py --slug demo --non-interactive --proceed

# 3) semantic (senza preview)
py src/semantic_onboarding.py --slug demo --no-preview --non-interactive

# 4) push (se vuoi testarlo)
# $env:GITHUB_TOKEN="<token>"; py src/onboarding_full.py --slug demo --non-interactive
```

> Nota: se vuoi usare Drive anche nello smoke dummy, carica qualche PDF real‑world nella cartella RAW su Drive del cliente `demo` prima del punto 2.

---

## 3) Esecuzione singolo orchestratore (quick)

```powershell
# pre-onboarding solo locale
py src/pre_onboarding.py --slug prova --name "Cliente Prova" --non-interactive --dry-run

# tag-onboarding locale
py src/tag_onboarding.py --slug prova --source local --non-interactive --proceed

# semantic (no preview)
py src/semantic_onboarding.py --slug prova --no-preview --non-interactive

# onboarding full (push) — richiede GITHUB_TOKEN
# $env:GITHUB_TOKEN="<token>"; py src/onboarding_full.py --slug prova --non-interactive
```

---

## 4) Pytest — guida completa

### Esecuzione globale

Esegue l'intera suite locale. Per default (vedi `pytest.ini`) vengono **esclusi** i test marcati `push` e `drive`.

```powershell
# tutto (locale):
pytest -ra

# includere i test push
pytest -ra -m "push"

# includere i test drive
pytest -ra -m "drive"
```

> Consiglio: in CI mantieni il default (no push/drive); in ambienti controllati abilita i marker quando hai le credenziali.

### Elenco dei file di test e come lanciarli

1. `tests/conftest.py`  
   Supporto: rende il repo importabile durante i test (aggiunge root e `src/` al `sys.path`). **Non si esegue da solo.**

2. `tests/test_unit_tags_validator.py`  
   Copre il validatore di `tags_reviewed.yaml` (`_validate_tags_reviewed` in `src/tag_onboarding.py`): campi obbligatori, duplicati case‑insensitive, caratteri illegali, `merge_into` senza target.
   ```powershell
   # file completo
   pytest tests	est_unit_tags_validator.py -ra
   # singolo test
   pytest tests	est_unit_tags_validator.py::test_validate_ok_minimal -ra
   ```

3. `tests/test_unit_book_guard.py`  
   Copre il preflight di pubblicazione (`_book_md_only_guard` in `src/onboarding_full.py`): accetta solo `.md`, ignora `.md.fp`, errore sugli altri formati.
   ```powershell
   pytest tests	est_unit_book_guard.py -ra
   pytest tests	est_unit_book_guard.py::test_book_guard_raises_on_non_md -ra
   ```

4. `tests/test_unit_emit_tags_csv.py`  
   Copre l’emissione CSV (`_emit_tags_csv`): header corretto, percorsi **POSIX** prefissati `raw/`, scrittura atomica.
   ```powershell
   pytest tests	est_unit_emit_tags_csv.py -ra
   ```

5. `tests/test_smoke_dummy_e2e.py` *(slow)*  
   Smoke end‑to‑end: `pre → dummy → tag (local) → semantic (no preview)` con assert minimi sui file generati.
   - **Prerequisito:** genera prima l’utente dummy (`py src/tools/gen_dummy_kb.py --slug <slug>`).
   - Marcato `@pytest.mark.slow`: va incluso esplicitamente.
   ```powershell
   # includi i test lenti
   pytest -ra -m "slow"
   # oppure per nome
   pytest -ra -k "dummy_e2e"
   ```

6. *(Opzionale)* `tests/test_contract_defaults.py`  
   Verifica che `tag_onboarding_main` abbia `source` **default = "drive"**.
   ```powershell
   pytest tests	est_contract_defaults.py -ra
   ```

### Testare una singola funzione


Puoi eseguire un test specifico indicando il **node id** `file::test_name` oppure filtrare per substring con `-k`.

```powershell
# esecuzione puntuale per node id
pytest tests	est_unit_tags_validator.py::test_validate_missing_keys -ra

# filtro per nome (substring)
pytest -k "book_guard and raises" -ra

# output più dettagliato
pytest -vv -k test_validate_ok_minimal
```

---

## 5) Log e pulizia rapida

```powershell
# ultimi log
Get-Content .\output\timmy-kb-*\logs\*.log -Tail 80

# pulizia sandbox di prova
Get-ChildItem .\output -Directory "timmy-kb-*" | Remove-Item -Recurse -Force
```

