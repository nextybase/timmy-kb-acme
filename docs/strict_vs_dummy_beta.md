# Modalità **Strict** e **Dummy** – Guida Operativa (Beta 1.0)

## Scopo del documento
Questo documento definisce **in modo operativo** il comportamento delle modalità **Strict** e **Dummy** nei flussi di onboarding (in particolare *tag_onboarding*), chiarendo **cosa è consentito**, **cosa è vietato** e **come viene tracciato nel Decision Ledger**.

L’obiettivo è evitare **ambiguità di stato**, **generazione implicita di artefatti** e **degrado silenzioso** durante la Beta.

---

## Principi invarianti (sempre validi)

- Il **Decision Ledger è la Single Source of Truth (SSoT)**.
- Ogni avanzamento di stato deve corrispondere a **lavoro realmente completato**.
- Nessuna generazione di artefatti “di comodo” nel percorso operativo standard.
- Ogni eccezione consentita deve essere:
  - **esplicita**
  - **auditabile**
  - **riconoscibile a posteriori**

---

## Modalità Strict (`TIMMY_BETA_STRICT`)

### Attivazione
Variabile d’ambiente:
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

## Regola d’oro
> Se nel Ledger leggi `TAGS_READY`, sai con certezza che è stato usato `--dummy`.

---

## Non previsto (intenzionale)
- Override automatici
- Fallback silenziosi
- Inferenza di stato fuori dal ledger
