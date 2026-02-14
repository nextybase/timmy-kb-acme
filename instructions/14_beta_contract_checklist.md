# Beta 1.0 Contract Checklist (Dev)

Questo documento definisce i **contratti tecnici non negoziabili** per la Beta 1.0 di Timmy KB.
Obiettivo: sistema **deterministico**, a **bassa entropia**, senza fallback impliciti.

---

## 1. Single Source of Truth (WorkspaceLayout)

Tutti i path canonici devono essere esposti dal layout.

Obbligatori:

- `layout.repo_root_dir`
- `layout.logs_dir`
- `layout.normalized_dir`
- `layout.book_dir`
- `layout.semantic_dir`
- `layout.vision_pdf`
- `layout.tags_db`

Regola:

> Nessun call-site deve usare `getattr(...)` o fallback su path calcolati.
> Se un path manca -> hard-fail.

---

## 2. Root deterministica (WORKSPACE_ROOT_DIR)

Il workspace root non è derivabile implicitamente.

- `WORKSPACE_ROOT_DIR` è obbligatorio
- Nessun fallback tipo `repo_root/output/timmy-kb-<slug>`

Regola:

> Una root. Un perimetro. Nessun universo alternativo.

---

## 3. No Signature Shims

Nessuna introspezione runtime della firma (`inspect.signature`) nei call-site CORE.

Esempi eliminati:

- `convert_md` fallback posizionale
- Drive download capability detection

Regola:

> Una funzione di servizio ha una firma unica e stabile.
> Firma non conforme -> hard-fail immediato.

---

## 4. Semantic Pipeline = Atomicità

La pipeline semantica è atomica:

- embeddings
- frontmatter enrichment
- entities extraction

Regola:

> O produce artefatti completi, o fallisce.
> Nessun "successo parziale".

### Embeddings

- errori embedding -> hard-fail (`ConfigError`/typed)
- nessun `return 0` su errore

### Frontmatter

- nessun `continue` su errori I/O
- config mapping non può degradare a `{}`

### Entities

- eliminato modello best-effort
- nessun `skipped=True`
- SpaCy/load/persist -> hard-fail typed

---

## 5. Artefatti CORE vs SERVICE_ONLY

Ogni artefatto deve appartenere a una classe:

- CORE: obbligatorio e deterministico
- CORE-GATE: prerequisito operativo
- SERVICE_ONLY: opzionale, non blocca il core

Regola Beta:

> Nessun downgrade implicito nel CORE o CORE-GATE.
> SERVICE_ONLY ammesso solo se esplicitamente isolato.

Riferimento: `instructions/13_artifacts_policy.md`

---

## 6. Vision Runner Sentinel Hash

Il gate Vision è deterministico.

Stati ammessi:

- sentinel mancante -> prima esecuzione (`None`)
- sentinel valido -> SHA-256 hex
- sentinel invalido -> evento `vision.hash_sentinel_invalid` + rerun forzato

Regola:

> Sentinel corrotto non degrada: forza sempre riesecuzione.

---

## 7. Logging e Diagnostica

Ogni hard-fail deve includere:

- slug
- file_path (quando disponibile)
- fase pipeline (es. `entities.persist`, `semantic.index.embed`)

Regola:

> Failure deterministica = failure auto-diagnostica.

---

## 8. Proibizioni Beta (Entropy Kill List)

Non ammessi in CORE:

- `except Exception: log + continue`
- `return 0` su errore operativo
- `mapping = {}` come fallback
- dual-path `x or default_path`
- capability detection via introspezione firma
- branch strict/non-strict runtime

---

## 9. Guardrail CI (minimi)

Ogni PR Beta deve garantire:

- `pre-commit run --all-files`
- `pytest`
- contract-test di superficie API (es. `tests/contract/test_semantic_api_contract.py`)
- grep invariants:

```bash
rg -n "getattr\(layout" src/
rg -n "inspect\.signature" src/
rg -n "skipped=True" src/
rg -n "mapping_all = \{\}" src/
```

Zero match nel CORE.

Nota scope:

- i guardrail anti-entropia (`tests/architecture/test_entropy_guards.py`) scansionano il CORE in `src/semantic` + `src/pipeline`, non la cartella `tests/`.
- pattern come `inspect.signature` sono vietati nei call-site runtime CORE, ma sono ammessi nei test contratto per verificare stabilit\u00e0 API.

---

## 10. Definition of Done (Beta)

Un run Beta è valido solo se:

- layout completo
- artefatti core prodotti
- nessun fallback legacy attivato
- failure immediata e typed su errore

Beta = determinismo operativo, non resilienza best-effort.
