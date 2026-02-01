# Strict vs Dummy Mode - Guida Operativa (Beta 1.0, Ledger SSoT)

Questo documento descrive un **vincolo strutturale della Beta 1.0 di Timmy-KB**.

Non e' una guida introduttiva ne' una modalita' di configurazione opzionale:
serve a chiarire **perche' il sistema, in Beta, e' intenzionalmente limitato**
e come interpretare correttamente i suoi comportamenti in termini di
governance, auditabilita' e stato del workspace.

## Perche' esistono Strict e Dummy

In Beta 1.0, Timmy-KB opera per default in **Strict Mode**.
Questo significa che l'esecuzione end-to-end della pipeline e'
volontariamente bloccata prima delle fasi di agency completa.

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

### Attivazione
Variabile d'ambiente:
```bash
TIMMY_BETA_STRICT=1
```

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

## Control Plane e Tools > Tuning

- Ogni pagina runtime mantiene `TIMMY_BETA_STRICT=1`; l'helper `ui.utils.control_plane.ensure_runtime_strict()` viene
  invocato durante il rendering del chrome (default di `render_chrome_then_require`) per bloccare l'esecuzione
  quando la variabile non è presente o vale `0`.
- L'interfaccia **Tools > Tuning** è dichiarata `strict_runtime=False` e segnalata come control plane. La pagina
  non esegue provisioning o update direttamente: raccoglie input e invia CLI isolati (`tools/tuning_pdf_to_yaml`,
  `tools/tuning_vision_provision`, `tools/tuning_system_prompt`) che girano con `control_plane_env(force_non_strict=True)`
  per mantenere l'ambiente deterministico.
- Ogni tool restituisce un JSON con schema obbligatorio (`status`, `mode`, `slug`, `action`, `errors`, `warnings`,
  `artifacts`, `paths`, `returncode`, `timmy_beta_strict`); i `paths` sono sempre deterministici (es. `output/<slug>/config/`).
- Gli helper `ui.utils.control_plane.run_control_plane_tool()` e `display_control_plane_result()` orchestrano la call e
  mostrano il payload nella UI, accompagnandola con messaggi di stato/warnings/errori.
- Qualsiasi altra pagina che girasse con `TIMMY_BETA_STRICT=0` nel runtime viene bloccata e registra l'anomalia nel ledger.

---

## Non previsto (intenzionale)
- Override automatici
- Fallback silenziosi
- Inferenza di stato fuori dal ledger
