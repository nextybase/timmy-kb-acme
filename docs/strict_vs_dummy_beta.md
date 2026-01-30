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
**Capability gate** (solo quando strict è spento):
```bash
TIMMY_ALLOW_DUMMY=1
```

### Comportamento
- Consente **solo esplicitamente** la generazione degli stub.
- Se `TIMMY_BETA_STRICT` è attivo, **non ha effetto**.
- Fuori dallo strict, l'uso di dummy è **capability-gated**: richiede `TIMMY_ALLOW_DUMMY=1`.

### Ledger
- `from_state = SEMANTIC_INGEST`
- `to_state   = SEMANTIC_INGEST` (intra-state)
- `normative_verdict = PASS` con `rationale = ok_dummy_mode` quando gli stub vengono generati
- `evidence_refs` include `dummy_mode:true`, `requested_mode:dummy`, `effective_mode:dummy`
- Se dummy è richiesto ma **non consentito** (capability mancante): `normative_verdict = BLOCK`
  con `stop_code = CAPABILITY_DUMMY_FORBIDDEN`.

### Quando usarla
- Demo end-to-end
- Sviluppo locale
- Test manuali

---

## Matrice riassuntiva

| Strict | --dummy | TIMMY_ALLOW_DUMMY | Esito |
|------|--------|-------------------|------|
| ✅ | ❌ | n/a | PASS (no stub) |
| ✅ | ✅ | n/a | PASS (dummy richiesto ma bloccato; no stub) |
| ❌ | ✅ | ✅ | PASS (stub generati; ok_dummy_mode) |
| ❌ | ✅ | ❌ | BLOCK (CAPABILITY_DUMMY_FORBIDDEN) |

---

## Regola d'oro
> Nel ledger non compaiono stati `TAGS_*`. Dummy è riconoscibile tramite `evidence_refs`
> (`requested_mode`, `effective_mode`, `dummy_mode`) e, quando negato, tramite `stop_code`.

---

## Non previsto (intenzionale)
- Override automatici
- Fallback silenziosi
- Inferenza di stato fuori dal ledger
