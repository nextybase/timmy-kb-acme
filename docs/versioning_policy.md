# Versioning & Release Policy – Timmy‑KB (v1.0.34 Stable)

Questa policy definisce **come versioniamo** e **come rilasciamo**. È allineata alla 1.0.3 (release di consolidamento) e alle modifiche di questa sessione. Obiettivo: evitare rotture non intenzionali e mantenere la documentazione sempre coerente con il codice.

---

## 1) Obiettivi
- Stabilità dei flussi degli orchestratori.
- Tracciabilità delle modifiche (CHANGELOG obbligatorio).
- Aggiornamento documentazione **nella stessa PR** del codice che cambia il comportamento.

---

## 2) Schema di versioning (SemVer “leggero”)
- **MAJOR (X.0.0)** – cambi **incompatibili** all’utente (es. rimozione di flag/CLI, modifiche al flusso degli orchestratori, struttura output).
- **MINOR (X.Y.0)** – nuove funzionalità **retro‑compatibili** (es. nuovi flag/env, miglioramenti preview/push senza cambiare default).
- **PATCH (X.Y.Z)** – bugfix, refactor interni, **pulizia** di script e **documentazione** senza impatto sul flusso.
> La **1.0.3** è una **PATCH**: rimozione di `print()` dagli orchestratori a favore del logger, pulizia preview e allineamento documentazione.

---

## 3) Criteri pratici per il bump
- **Aggiungi un flag CLI** senza cambiare i default → **MINOR**.
- **Deprecazione** di un flag (es. `--skip-*`) mantenendone il supporto con **warning** → **MINOR**.
- **Rimozione** di un flag deprecato → **MAJOR** (preavviso nella doc almeno una minor prima).
- Cambi nel **comportamento di default** (es. anteprima obbligatoria in batch) → **MAJOR**.
- Solo **logging**/pulizia import/exit codes invariati → **PATCH**.
- Nuovi **Exit Codes** o rimappature che non rompono i caller → **MINOR** (documentare bene).
- Cambi nella **struttura dell’output** (`book/`, `config/`, `logs/`) → **MAJOR**.

---

## 4) Rilascio (artefatti e checklist)
Ogni rilascio deve includere:
1. **Tag Git** `vX.Y.Z` sul branch di default (da `GIT_DEFAULT_BRANCH`, fallback `main`).
2. **CHANGELOG.md** aggiornato con data, sezioni *Added/Changed/Fixed/Deprecated/Removed/Security*.
3. **Documentazione** aggiornata (`README.md` e `docs/*`) nella **stessa PR** delle modifiche.
4. Verifica che la pipeline passi i **test manuali** minimi (dry‑run, no‑drive, interattivo, non‑interattivo).

Esempio di tagging post‑merge:
```bash
git checkout $(git rev-parse --abbrev-ref HEAD)   # sul default branch
git pull
git tag -a v1.0.3 -m "Timmy-KB 1.0.3 – consolidamento orchestratori e docs"
git push --tags
```

---

## 5) Deprecation Policy
- Un elemento marcato **Deprecated** resta supportato per **almeno una versione MINOR** (es. introdotto deprecato in 1.1.x → rimozione non prima di 1.2.0).
- I deprecati **non** vengono rimossi in PATCH.
- La documentazione deve indicare l’alternativa consigliata e lo **scope temporale** della rimozione.
- Caso attuale: `--skip-drive` / `--skip-push` → **deprecati**; continuano a funzionare con warning. L’alternativa è `--no-drive` / `--no-push`. La rimozione sarà annunciata con **preavviso** in una release MINOR prima di una rimozione **MAJOR**.

---

## 6) CHANGELOG: regole editoriali
- Scrivi voci **brevi** e orientate all’utente.
- Usa i tempi **al passato**; includi la data in ISO (YYYY‑MM‑DD).
- Collega PR/issue quando utile.
- Ogni entry deve indicare se richiede **azioni** per l’utente (migrazione, nuove variabili).

Struttura consigliata:
```markdown
## [1.0.3] – 2025-08-17
### Added
- …

### Changed
- …

### Fixed
- …

### Deprecated
- …

### Removed
- …

### Security
- …
```

---

## 7) Allineamento con CI/CD (facoltativo)
- Opzionale: un job che blocca il merge se `docs/` o `README.md` non sono aggiornati quando cambiano CLI/comportamenti.
- Opzionale: un check per presenza e formato della voce in `CHANGELOG.md`.

---

**Stato:** policy attiva dalla v1.0.4. Le prossime release dovranno rispettarla.
