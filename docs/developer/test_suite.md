# Testing Strategy -- FAST / ARCH / FULL

Questa pagina è **normativa**. Definisce lo scopo e l'uso dei tre binari di test per garantire **determinismo**, **bassa entropia** e **cicli di feedback coerenti** con la Beta.

## Principi guida

- **Determinismo prima della copertura massima**: un test instabile non è un test utile.
- **Bassa entropia**: pochi comandi ufficiali, stessi marker, niente logica duplicata.
- **Separazione dei cicli**: inner loop veloce, invarianti strutturali/contratti, suite completa.
- **Strict-first**: per default i test girano in modalità strict (salvo test che dichiarano esplicitamente il non-strict).

---

## Interfaccia ufficiale (Python)

La fonte di verità è lo script cross-platform:

```bash
python tools/test_runner.py fast
python tools/test_runner.py arch
python tools/test_runner.py full
python tools/test_runner.py linux
```

Il Makefile è solo un alias comodo:

```bash
make test-fast
make test-arch
make test-full
```

**Regola**: non duplicare altrove la logica di selezione (niente script paralleli, niente comandi "simili ma diversi").

---

## Prerequisiti opzionali e skip deterministici

Questa sezione descrive gli skip **attesi** (non "incidenti"):

- **e2e**: richiede Playwright + Chromium (`playwright install chromium`) oltre alle dipendenze dev.
- **drive**: richiede variabili (`SERVICE_ACCOUNT_FILE`, `DRIVE_ID`) e dipendenze Google (extra/dev).
- **Windows**: alcuni test basati su symlink possono essere skippati in modo deterministico.

**Regola**: se una capability opzionale non è presente, lo skip deve essere **esplicito e spiegabile** (marker + import or skip + messaggio chiaro), mai un fallback silenzioso.

---

## FAST (inner loop)

**Scopo**: feedback rapido durante lo sviluppo.

- Include **solo** test marcati `unit`.
- Esclude sempre `slow`.

Comando:

```bash
python tools/test_runner.py fast
```

**Regola**: se un test deve girare nell'inner loop, deve essere marcato `unit`. Se manca il marker, **non è garantito** in FAST.

**Nota pratica**: il fatto che un test sia "veloce" non basta; deve anche essere **stabile** e non dipendere da integrazioni opzionali.

---

## ARCH (invarianti) + CONTRACT (gating/contratti)

**Scopo**: verificare invarianti strutturali e contratti di comportamento che riducono l'entropia del sistema.

Comando:

```bash
python tools/test_runner.py arch
```

### Cosa include

- **ARCH**: import-safety, encoding, confini (path-safety), prerequisiti strict.
- **CONTRACT**: contratti di interfaccia e gating (es. UI wrapper contract, readiness, clamping coerente), snapshot/shape di output dove esiste un contratto esplicito.

### Disciplina di scrittura

- Un test `contract` deve testare **comportamento reale** (non ricostruire la logica a mano).
- Se un test è "tautologico" (verifica solo che i file creati esistano), va eliminato o riscritto.

**Esempio reale di pulizia fatta**: abbiamo rimosso un test UI che non invocava mai la funzione di produzione e duplicava la logica nel test.

---

## FULL

**Scopo**: suite completa deterministica prima del push o della consegna.

Comando:

```bash
python tools/test_runner.py full
```

**Regola**: FULL deve essere affidabile, ripetibile e "non sorprendente". Se un test è flaky, va reso deterministico oppure spostato/isolato (o rimosso se non porta valore reale).

---

## Linux (Docker)

**Scopo**: validare localmente il comportamento target Linux prima del push, includendo pre-commit + suite pytest completa in container.

Prerequisito:

- Docker disponibile in PATH.

Comando:

```bash
python tools/test_runner.py linux
```

---

## Marker (significato semantico)

I marker sono la semantica ufficiale della suite. Usali per:

- selezionare subset mirati;
- evitare sessioni inutilmente lunghe;
- mantenere il contratto tra test e binari.

Marker principali:

- `unit`: inner loop (FAST).
- `slow`: test lenti o costosi (mai in FAST).
- `arch`: invarianti architetturali (import, encoding, confini).
- `contract`: contratti UI/gating/shape dove normato.
- `pipeline`: integrazione pipeline core.
- `semantic`: comportamento modulo semantic.
- `ui`: superficie Streamlit/UI.
- `ai`: configurazioni/risoluzione AI e runner associati.
- `retriever`: retriever (scoring/top-k/guardrail/preview).
- `scripts`: guardrail su script/quality gates.
- `tools`: strumenti CLI/utility.
- `drive`: integrazione Google Drive.
- `e2e`: end-to-end Playwright.

### Come vengono assegnati i marker

- **Per path** (preferito): cartelle dedicate (`tests/ui`, `tests/pipeline`, `tests/contract`, ecc.).
- **Per prefisso file** (supporto): `test_ui_…`, `test_pipeline_…`, `test_retriever_…`.

**Regola**: evitare regole special-case su file specifici, perché aumentano l'entropia. Teniamo solo eccezioni rare e motivate.

**Esempio reale di pulizia fatta**: abbiamo rimosso in `conftest.py` riferimenti a file non più esistenti, lasciando marking quasi interamente path/prefix-based.

---

## Disciplina performance

Soglia consigliata: \~1s. Se un test supera stabilmente 1s:

- marcarlo `slow`;
- rimuoverlo da `unit` se presente.

Comando consigliato:

```bash
pytest -q --durations=20 --durations-min=1.0
```

**Regola**: meglio 10 test deterministici e rapidi che 1 test "onnicomprensivo" e lento.

---

## Workflow consigliato

- Durante lo sviluppo: `python tools/test_runner.py fast`
- A fine task o change importante: `python tools/test_runner.py arch`
- Prima del push: `python tools/test_runner.py full`

**Suggerimento**: se stai lavorando su un'area specifica (es. retriever), usa anche selezione diretta:

```bash
pytest -q -m retriever
```

---

## Pre-commit / pre-push hooks

Gli hook Git coordinano formattazione, linting e test preliminari senza costringere a lanciare manualmente l'intera suite.

### Installazione

```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
```

Su macchine nuove, prima di lanciare `pre-commit`, esporta anche:

```bash
export TIMMY_OBSERVABILITY_CONFIG=tools/smoke/fixtures/observability.ci.yaml
```

```powershell
$env:TIMMY_OBSERVABILITY_CONFIG="tools/smoke/fixtures/observability.ci.yaml"
```

### Debug (quando fallisce il pre-push)

```bash
pre-commit run --hook-stage pre-push --all-files
```

### Hook chiave e scopi

| Hook                                                   | Stage                 | Descrizione                                                         |
| ------------------------------------------------------ | --------------------- | ------------------------------------------------------------------- |
| `pytest-fast`                                          | pre-commit            | invoca `python tools/test_runner.py fast` (solo `unit`, non `slow`) |
| `pytest-full`                                          | pre-push              | invoca `python tools/test_runner.py full`                           |
| `black`, `ruff`, `isort`, `mypy`, `cspell`, `qa-safe`… | pre-commit / pre-push | formattazione, linting, disciplina (vedi `.pre-commit-config.yaml`) |

### Comportamento atteso

- `fast` gira prima di ogni commit.
- `full` gira prima di ogni push.
- hook aggiuntivi (`streamlit-ui-guard`, `detect-secrets`, `forbid-path-write-text-bytes`, ecc.) aggiungono vigilance specifiche.

### Suggerimenti operativi

- In caso di failure: eseguire `pre-commit run --all-files` per isolare il tool in errore.
- Prima di un changelog "macro": ripetere `pre-commit run --hook-stage pre-push --all-files`.

---

## Regole di manutenzione della suite (anti-entropia)

Queste regole sono normative e riflettono quanto abbiamo già applicato:

1. **Elimina i test tautologici** (non invocano produzione, duplicano logica nei test).
2. **Evita duplicazioni strict/non-strict**: usa parametrize quando serve.
3. **Coerenza marker/naming**: se un test è `contract + pipeline`, dichiaralo esplicitamente (marker), non affidarti al nome.
4. **Riduci special-case in conftest**: preferisci path/prefix.
5. **Ogni fix anti-drift deve avere un test guardia** (es.: clamp preview candidate\_limit).

---

## Appendice: esempi di casi recenti (per memoria di progetto)

- `build_tags_csv` è stato riclassificato come **contract + pipeline** (marker espliciti).
- `preview_effective_candidate_limit` è stato allineato al runtime con clamping e test di regressione.
- `vocab_loader` deduplica alias in modo case-insensitive per ridurre drift.
- log di retriever include `embedding_model` già da l'evento "started" per audit più robusto.
