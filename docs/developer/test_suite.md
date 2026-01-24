# Testing Strategy - FAST / ARCH / FULL

Questa pagina e' normativa. Definisce lo scopo e l'uso dei tre binari
di test per garantire determinismo, bassa entropia e cicli di feedback
coerenti con la Beta.

## Principi guida
- Determinismo prima di copertura massima: un test instabile non e' un test utile.
- Bassa entropia: pochi comandi ufficiali, stessi marker, nessuna logica duplicata.
- Separazione dei cicli: inner loop veloce, invarianti strutturali, suite completa.

## Interfaccia ufficiale (Python)
La fonte di verita' e' lo script cross-platform:
```bash
python tools/test_runner.py fast
python tools/test_runner.py arch
python tools/test_runner.py full
```
Il Makefile e' solo un alias comodo:
```bash
make test-fast
make test-arch
make test-full
```
Non duplicare la logica dei comandi altrove.

## Prerequisiti opzionali e skip deterministici
Questa sezione e' minima e serve a chiarire i casi attesi:
- e2e: richiede Playwright + Chromium (`playwright install chromium`) oltre alle deps dev.
- drive: richiede `SERVICE_ACCOUNT_FILE`, `DRIVE_ID` e dipendenze Google (requirements-dev).
- Windows: alcuni test basati su symlink sono skippati in modo deterministico; e' atteso.

## FAST (inner loop)
Scopo: feedback rapido durante lo sviluppo.
- Include solo test marcati `unit`.
- Esclude sempre `slow`.
Comando:
```bash
python tools/test_runner.py fast
```
Regola: se un test deve girare nell'inner loop, deve essere marcato `unit`.
In assenza del marker, non e' garantito in FAST.

## ARCH / CONTRACT
Scopo: invarianti strutturali, import-safety, encoding, contratti di UI/gating.
Comando:
```bash
python tools/test_runner.py arch
```

## FULL
Scopo: suite completa deterministica prima del push o della consegna.
Comando:
```bash
python tools/test_runner.py full
```

## Marker (significato semantico)
- `unit`: test unitari per l'inner loop (FAST).
- `slow`: test lenti, smoke o end-to-end (mai in FAST).
- `arch`: invarianti architetturali (import, encoding, confini).
- `contract`: snapshot/contratti UI e gating.
- `pipeline`: integrazione pipeline core.
- `semantic`: comportamento del modulo semantic.
- `ui`: superficie Streamlit/UI.
- `ai`: configurazioni/risoluzione AI e runner associati.
- `retriever`: scoring/top-k/guardrail del retriever.
- `scripts`: test su script/guardrail di qualita'.
- `tools`: test su strumenti CLI/utility.
- `drive`: richiede Drive (SERVICE_ACCOUNT_FILE, DRIVE_ID).
- `e2e`: end-to-end con Playwright.

## Disciplina performance
Soglia consigliata: ~1s. Se un test supera stabilmente 1s:
- marcarlo `slow`;
- rimuoverlo da `unit` se presente.
Comando suggerito:
```bash
pytest -q --durations=20 --durations-min=1.0
```

## Workflow consigliato
- Durante lo sviluppo: `python tools/test_runner.py fast`
- A fine task o change importante: `python tools/test_runner.py arch`
- Prima del push: `python tools/test_runner.py full`

## Pre-commit / pre-push
Installazione hook:
```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
```
Debug pre-push:
```bash
pre-commit run --hook-stage pre-push --all-files
```
Serve a riprodurre localmente FULL senza pushare.
Comportamento:
- pre-commit: `python tools/test_runner.py fast`
- pre-push: `python tools/test_runner.py full`
