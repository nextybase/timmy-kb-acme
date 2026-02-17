# Testing Strategy -- FAST / ARCH / FULL (Low-Entropy)

Questa pagina è **normativa**. Definisce scopi, comandi e disciplina della suite di test per garantire **determinismo**, **bassa entropia** e cicli di feedback coerenti con la Beta.

## Principi guida

- **Determinismo prima della copertura massima**: un test instabile è rumore.
- **Bassa entropia**: pochi comandi ufficiali, niente selezioni duplicate "simili ma diverse".
- **Fail-loud**: niente fallback silenziosi; errori tipizzati e messaggi chiari.
- **Strict-first**: i test girano in strict per default. Il nonstrict è consentito solo se **dichiarato esplicitamente** dal test.
- **Ambiente controllato**: su macchina dedicata l'ambiente è "fissato"; le verifiche di attestation/preflight sono strutturali, non cosmetiche.

---

## Interfaccia ufficiale (Python)

La fonte di verità è lo script cross-platform:

```bash
python tools/test_runner.py fast
python tools/test_runner.py arch
python tools/test_runner.py full
python tools/test_runner.py linux
```

Il Makefile (se presente) è solo un alias comodo: **non** deve introdurre logiche proprie.

**Regola**: non duplicare altrove la logica di selezione (niente script paralleli, niente comandi "quasi uguali").

---

## Prerequisiti opzionali e skip deterministici

Questa sezione descrive gli skip **attesi** (non "incidenti"):

- **e2e**: richiede Playwright + Chromium (`playwright install chromium`) oltre alle dipendenze dev.
- **drive**: richiede variabili e dipendenze Google (extra/dev). In assenza, i test devono **skippare esplicitamente** con messaggio chiaro.
- **Windows**: alcuni test basati su symlink possono essere skippati in modo deterministico.

**Regola**: se una capability opzionale non è presente, lo skip deve essere **esplicito e spiegabile** (marker + skip con messaggio). Mai "degrado" silenzioso.

---

## FAST

**Scopo**: feedback rapido durante lo sviluppo (inner loop) senza dipendere da marker "positivi".

Selezione:

- include tutti i test **non** marcati `slow`, `e2e`, `drive`.

Comando:

```bash
python tools/test_runner.py fast
```

**Regola**: un test "veloce" non deve dipendere dal marker `unit` per entrare in FAST. `unit` resta opzionale come semantica, ma non è più un gate.

---

## ARCH (invarianti) + CONTRACT (gating/contratti)

**Scopo**: verificare invarianti strutturali e contratti che riducono l'entropia del sistema e impediscono reintroduzioni di shim/fallback.

Comando:

```bash
python tools/test_runner.py arch
```

### Cosa include

- **ARCH**: import-safety, encoding, path-safety, confini tra layer (UI/runtime), disciplina strict.
- **CONTRACT**: contratti di interfaccia e gating (shape/output normati, confini UI, readiness), dove esiste un contratto esplicito.

### Guardrail architetturali (antientropia)

La suite contiene guardrail che agiscono come "lint di architettura":

- divieti su pattern di fallback silenzioso (es. `except Exception: pass`, "ritorni vuoti" dentro except in core);
- divieti su pattern che introducono variabilità/shim non ammessa nel core (es. introspezioni o negotiation layer in percorsi critici);
- disciplina "strictness" (keyword e bypass non ammessi in core).

**Regola**: questi guardrail sono parte del contratto Beta. Se un cambiamento li rompe, la soluzione non è "ammorbidirli", ma riallineare il codice alla policy.

### Disciplina di scrittura

- Un test `contract` deve verificare **comportamento reale**, non ricostruire la logica di produzione "a mano".
- Se un test è tautologico (verifica solo che "esista un file" senza esercitare il comportamento), va eliminato o riscritto.

---

## FULL

**Scopo**: suite completa deterministica prima del push o della consegna.

Comando:

```bash
python tools/test_runner.py full
```

Selezione corrente:

- FULL include anche gli `slow`;
- FULL continua a escludere `e2e` e `drive` nel runner locale (capability opzionali).

**Regola**: FULL deve essere affidabile, ripetibile e "non sorprendente". Se un test è flaky, va reso deterministico oppure isolato come `e2e/drive/slow` (o rimosso se non porta segnale reale).

---

## NEGATIVE (deprecato)

Storicamente esisteva un binario "negative" per correre in modo mirato test che provano condizioni vietate (shim/fallback/legacy).

**Stato attuale**: non è più una categoria privilegiata e non deve guidare nuove scelte di design.

- Non aggiungere nuovi test marcati `negative`.
- Se devi testare un divieto o un confine, usa `arch`/`contract` e un nome test esplicito "fails when ".
- I test "antishim/antifallback" devono vivere come guardrail architetturali (ARCH) o contratti (CONTRACT), non come suite separata.

**Obiettivo**: rimuovere del tutto il concetto operativo di `negative` nella traiettoria verso la 1.0.

---

## Linux (Docker)

**Scopo**: validare localmente il comportamento target Linux prima del push, includendo disciplina (pre-commit) e suite pytest in container.

Prerequisito:

- Docker disponibile in PATH.

Comando:

```bash
python tools/test_runner.py linux
```

---

## Marker (semantica)

I marker sono la semantica ufficiale della suite. Usali per:

- selezione mirata (quando serve davvero);
- evitare sessioni inutilmente lunghe;
- mantenere il contratto tra test e binari.

Marker tipici:

- `slow`: test lenti o costosi.
- `arch`: invarianti architetturali (import/encoding/confini/path-safety/anti-entropia).
- `contract`: contratti UI/gating/shape dove normato.
- `pipeline`, `semantic`, `ui`, `ai`, `retriever`, `scripts`, `tools`: domini funzionali.
- `drive`, `e2e`: capability opzionali.

### Come vengono assegnati i marker

- **Per path** (preferito): cartelle dedicate (`tests/ui`, `tests/pipeline`, `tests/semantic`, ).
- **Per prefisso file** (supporto): `test_ui_`, `test_pipeline_`, ecc.

**Regola**: evitare regole special-case su singoli file in `conftest`, perché aumentano l'entropia. Preferire path/prefix.

---

## Disciplina performance

Soglia consigliata per inner loop: ~1s per test.

Se un test supera stabilmente 1s:

- marcarlo `slow`;
- ridurlo (fixture più piccole, meno IO) oppure spostarlo dove ha senso.

Comando consigliato:

```bash
pytest -q --durations=20 --durations-min=1.0
```

**Regola**: meglio 20 test piccoli e deterministici che 1 test onnivoro e lento.

---

## Workflow consigliato

- Durante lo sviluppo: `python tools/test_runner.py fast`
- Quando tocchi confini/contratti/anti-entropia: `python tools/test_runner.py arch`
- Prima del push: `python tools/test_runner.py full`

**Suggerimento**: quando lavori su un'area, usa selezione diretta per domini:

```bash
pytest -q -m ui
pytest -q -m pipeline
pytest -q -m semantic
```

---

## Pre-commit / pre-push hooks

Gli hook Git coordinano formattazione, linting e test preliminari.

### Installazione

```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
```

Se richiesto dal setup locale/CI, esporta anche:

```bash
export TIMMY_OBSERVABILITY_CONFIG=tools/smoke/fixtures/observability.ci.yaml
```

PowerShell:

```powershell
$env:TIMMY_OBSERVABILITY_CONFIG="tools/smoke/fixtures/observability.ci.yaml"
```

### Debug (quando fallisce il pre-push)

```bash
pre-commit run --hook-stage pre-push --all-files
```

### Hook chiave e scopi

| Hook | Stage | Descrizione |
| --- | --- | --- |
| `pytest-fast` | pre-commit | invoca `python tools/test_runner.py fast` (`not slow and not e2e and not drive`) |
| `pytest-full` | pre-push | invoca `python tools/test_runner.py full` (`not e2e and not drive`, include `slow`) |
| `black`, `ruff`, `isort`, `mypy`, `cspell`, `qa-safe` | pre-commit / pre-push | formattazione, linting, disciplina (vedi `.pre-commit-config.yaml`) |

### Comportamento atteso

- `fast` gira prima di ogni commit.
- `full` gira prima di ogni push.
- hook aggiuntivi applicano guardrail mirati (UI boundary, secrets, path discipline, ecc.).

---

## Regole di manutenzione della suite (anti-entropia)

1) **Elimina i test tautologici** (non invocano produzione, duplicano logica nel test).
2) **Evita duplicazioni meccaniche**: estrai helper quando lo setup si ripete (dotenv, workspace tmp, logger, ecc.).
3) **Un test, una causa, un'asserzione chiara**: niente test "multipurpose" che coprono cinque failure mode.
4) **Preferisci path/prefix per marker**: riduci eccezioni e listoni in `conftest`.
5) **Strict-first sempre**: il nonstrict deve essere esplicito, locale e motivato.
6) **Niente shim "perché forse"**: in Beta, se una capability non c'è, si skippa o si hard-fail in modo chiaro (mai negotiation layer in core).

---

## Appendice: esempi di casi ricorrenti

- Se una feature è opzionale (Drive/E2E), i test devono essere marcati e skippare in modo deterministico quando manca la capability.
- Se un comportamento è "policy" (anti-fallback/anti-shim), preferisci guardrail ARCH/CONTRACT invece di suite parallele.
- Quando un'invariante viene rotta, aggiungi un test *guardia* minimale e mirato (non una mini-implementazione della feature nel test).
