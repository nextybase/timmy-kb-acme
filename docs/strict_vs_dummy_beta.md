# Strict vs Dummy Mode - Guida Operativa (Beta 1.0)

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
- Il flusso di *tag_onboarding*:
  - può arrivare **al massimo** a `TAGS_CSV_READY`
  - **non** può raggiungere `TAGS_READY`

### Ledger
- `to_state = TAGS_CSV_READY`
- `verdict = ALLOW`
- `rationale = checkpoint_proceeded_no_stub`

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
- Se `TIMMY_BETA_STRICT` è attivo, **non ha effetto**.

### Ledger
- `to_state = TAGS_READY`
- `verdict = ALLOW`
- `rationale = ok_dummy_mode`
- `evidence_json.dummy_mode = true`

### Quando usarla
- Demo end-to-end
- Sviluppo locale
- Test manuali

---

## Matrice riassuntiva

| Strict | Dummy | Stato finale |
|------|-------|--------------|
| ❌ | ❌ | TAGS_CSV_READY |
| ✅ | ❌ | TAGS_CSV_READY |
| ❌ | ✅ | TAGS_READY |
| ✅ | ✅ | TAGS_CSV_READY |

---

## Regola d'oro
> Se nel Ledger leggi `TAGS_READY`, sai con certezza che è stato usato `--dummy`.

---

## Non previsto (intenzionale)
- Override automatici
- Fallback silenziosi
- Inferenza di stato fuori dal ledger
