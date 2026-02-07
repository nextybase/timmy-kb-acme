# Strict vs Dummy Mode - Guida Operativa (Beta 1.0, Ledger SSoT)

Questo documento descrive un **vincolo strutturale della Beta 1.0 di Timmy-KB**.

Non e' una guida introduttiva ne' una modalita' di configurazione opzionale:
serve a chiarire **perche' il sistema, in Beta, e' intenzionalmente limitato**
e come interpretare correttamente i suoi comportamenti in termini di
governance, auditabilita' e stato del workspace.

## Perche' esistono Strict e Dummy

In Beta 1.0, Timmy-KB opera per default in **Strict Mode**, e la pipeline rimane
bloccata sulle fasi di agency completa finché non viene concessa un'eccezione.
L'assenza o la stringa vuota di `TIMMY_BETA_STRICT` viene interpretata come
strict; solo un valore esplicitamente falsy (`0`, `false`, `no`, `off`)
autorizza un'esecuzione non-strict mirata e auditabile.

La **Dummy Mode** non e' una modalita' "piu' permissiva":
e' un'eccezione esplicita, tracciata e auditabile, pensata esclusivamente
per test, demo e validazioni controllate.

Ogni uso della Dummy Mode:
- richiede un flag esplicito,
- e' registrato nel Decision Ledger,
- non puo' essere confuso con un'esecuzione reale in ambiente operativo.

Se stai usando Timmy-KB in Beta e ti chiedi "perche' il flusso si ferma qui",
la risposta e' quasi sempre in questo documento.

---

## Principi invarianti (sempre validi)

- Il **Decision Ledger è la Single Source of Truth (SSoT)**.
- Ogni avanzamento di stato deve corrispondere a **lavoro realmente completato**.
- Nessuna generazione di artefatti "di comodo" nel percorso operativo standard.
- Ogni eccezione consentita deve essere:
  - **esplicita**
  - **auditabile**
  - **riconoscibile a posteriori**

---

## Modalità Strict (`TIMMY_BETA_STRICT`)

### Attivazione e default implicito
Strict è attivo anche senza variabili:
```bash
TIMMY_BETA_STRICT=1
```
o, in mancanza della flag, per default. Solo valori falsy espliciti (`0`, `false`, `no`, `off`)
disabilitano la stringa strict per quella run.

### Comportamento
- Modalità **raccomandata di default** per la Beta.
- Blocca **qualsiasi generazione di stub semantici**.
- Il gate `tag_onboarding` resta **intra-state** su `SEMANTIC_INGEST` (nessuna transizione di stato nel ledger).
- In strict, una richiesta `--dummy` è **tracciata** ma non produce stub.

### Ledger
- `from_state = SEMANTIC_INGEST`
- `to_state   = SEMANTIC_INGEST`  (intra-state; *State Model SSoT*)
- `normative_verdict = PASS`
- `rationale` deterministica (es. `dummy_blocked_by_strict` / `checkpoint_proceeded_no_stub`)
- `evidence_refs` include `requested_mode:*` e `effective_mode:*`

### Quando usarla
- Ambienti reali
- Beta pubblica
- Audit e governance
- Test di processo

---



## Modalità Dummy (`--dummy`)

### Attivazione
Flag CLI esplicito:
```bash
timmy-kb tag-onboarding ... --dummy
```

### Comportamento
- Consente **solo esplicitamente** la generazione degli stub.
- Nel tooling dummy, `TIMMY_BETA_STRICT` viene forzato a `0` solo per il processo **se non** si usa `--deep-testing` (override locale).
- Se Drive non è disponibile, usa `--no-drive` (CLI) o **Solo locale** (UI) per la Dummy; in **deep-testing** Drive deve essere configurato.

### Ledger
- `from_state = SEMANTIC_INGEST`
- `to_state   = SEMANTIC_INGEST` (intra-state)
- `normative_verdict = PASS` con `rationale = ok_dummy_mode` quando gli stub vengono generati
- `evidence_refs` include `dummy_mode:true`, `requested_mode:dummy`, `effective_mode:dummy`

### Quando usarla
- Demo end-to-end
- Sviluppo locale
- Test manuali

---

## Matrice riassuntiva

| Strict | --dummy | Esito |
|------|--------|------|
| SI | NO | PASS (no stub) |
| SI | SI | PASS (deep-testing: strict reale; no override) |
| NO | SI | PASS (override locale; ok_dummy_mode) |

---

## Regola d'oro
> Nel ledger non compaiono stati `TAGS_*`. Dummy è riconoscibile tramite `evidence_refs`
> (`requested_mode`, `effective_mode`, `dummy_mode`) e, quando negato, tramite `stop_code`.

## Policy Beta A
- **Strict per default:** l'assenza della variabile `TIMMY_BETA_STRICT` o una stringa vuota equivale a strict; solo valori falsy espliciti (`0`, `false`, `no`, `off`) disattivano la modalità strict per lo step corrente.
- **Tool non manipolano il flag:** nessun tool modifica `TIMMY_BETA_STRICT` globalmente. Le deroghe sono sempre step-scoped e limitate al contesto del tool.
- **Deroghe auditabili:** quando serve un contesto non-strict si invoca `tools/non_strict_step.py` con gli step whitelist (`vision_enrichment`, `prompt_tuning`, `pdf_to_yaml_tuning`); l'helper registra `non_strict_step` nel ledger se il layout è disponibile, altrimenti emette log strutturati con gli stessi campi (`step`, `reason_code`, `strict_output`, `status`).
- **Bootstrap deterministic default:** quando il `ClientContext` non è disponibile (es. prima di creare il workspace) la decisione `decisions.vision_strict_output` mantiene `effective=true` e `rationale="default_true_bootstrap_phase"` con `source="bootstrap_default"` per evidenziare che si tratta di un default intenzionale e non di un errore.

## Control Plane e Tools > Tuning

- Ogni pagina runtime utilizza `ensure_runtime_strict()` per confermare strict: la guardia
  considera strict anche l'assenza/valore vuoto di `TIMMY_BETA_STRICT` e blocca solo se il flag è
  esplicitamente `0`, `false`, `no` o `off`.
- L'interfaccia **Tools > Tuning** è dichiarata `strict_runtime=False` e segnalata come control plane. La pagina
  raccoglie input e invia CLI isolati (`tools/tuning_pdf_to_yaml`, `tools/tuning_vision_provision`, `tools/tuning_system_prompt`)
  senza mai modificare `TIMMY_BETA_STRICT`. Quando serve un contesto non-strict viene usato `tools/non_strict_step.py`
  con gli step whitelist (`vision_enrichment`, `prompt_tuning`, `pdf_to_yaml_tuning`); l'eccezione è confinata allo step,
  tracciata nel ledger (`non_strict_step`) quando il layout è disponibile o, in assenza di workspace, con log strutturati.
- Ogni tool restituisce un JSON con schema obbligatorio (`status`, `mode`, `slug`, `action`, `errors`, `warnings`,
  `artifacts`, `paths`, `returncode`, `timmy_beta_strict`); i `paths` sono sempre deterministici (es. `output/<slug>/config/`).
- Gli helper `ui.utils.control_plane.run_control_plane_tool()` e `display_control_plane_result()` orchestrano la call e
  mostrano il payload nella UI, accompagnandola con messaggi di stato/warnings/errori.
-- Qualsiasi altra pagina che girasse con `TIMMY_BETA_STRICT=0` nel runtime viene bloccata e registra l'anomalia nel ledger.

## CI vs Local/Test harness
- **CI import-smoke:** il gate `Guard strict runtime` in `.github/workflows/import-smoke.yml` blocca qualsiasi valore non consentito di `TIMMY_BETA_STRICT`, garantendo che il flag resti un invariante nelle run di import.
- **Local e Tools > Tuning:** la UI control-plane non disattiva `TIMMY_BETA_STRICT`; ogni deroga viene eseguita attraverso `tools/non_strict_step.py`, rimanendo step-scoped e lasciando traccia (`non_strict_step`) nel ledger o nei log strutturati quando il layout/slug non è disponibile.
- **Test harness:** alcune suite (per esempio `tools/test_runner.py`) impostano `TIMMY_BETA_STRICT=0` per coprire branch non-strict, ma quel comportamento è confinato ai test e **non** deve essere replicato dai tool di runtime o dalla UI.
 - **Dummy health metrics:** il payload dummy espone `health.local_readmes_count`, `health.drive_readmes_count` e `health.readmes_count` (il totale); `drive_readmes` contiene il dettaglio raccolto da Drive mentre `local_readmes` raccoglie i file creati internamente, così i contatori rimangono coerenti anche con i dati Telemetry.

---

## Non previsto (intenzionale)
- Override automatici
- Fallback silenziosi
- Inferenza di stato fuori dal ledger
