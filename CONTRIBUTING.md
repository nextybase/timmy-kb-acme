# Contributing Guide — Timmy-KB

Grazie per contribuire a Timmy-KB! Questo documento definisce le regole **operative** per contribuire in modo consistente e sicuro, allineate alla documentazione in `/docs` e al flusso di pipeline.

## Principi di base
- **Separa orchestrazione e moduli**: gli orchestratori gestiscono UX/CLI (prompt, conferme, mapping errori); i moduli eseguono azioni tecniche e **non** fanno prompt né terminano il processo.
- **Logging centralizzato**: usa sempre `logging_utils.get_structured_logger`; l’uso di `print()` è vietato. I segreti non devono mai comparire nei log.
- **Modalità**: in `--non-interactive` nessun prompt; comportamento deterministico (preview auto-skip se Docker assente, push disabilitato salvo `--push`).
- **Sicurezza I/O**: valida percorsi con `is_safe_subpath`, usa scritture atomiche, non serializzare segreti su disco.
- **Doc e codice insieme**: ogni modifica al comportamento richiede aggiornare contestualmente la documentazione correlata in `/docs` e il `README.md`.

## Branching e versioning
- **Branch di base**: letto da `GIT_DEFAULT_BRANCH` (fallback `main`).
- **SemVer leggero**: MAJOR (breaking), MINOR (feature compatibile), PATCH (bugfix/refactor interno). Mantieni **retrocompatibilità** quando possibile.
- Ogni release deve aggiornare **CHANGELOG.md** con note brevi e orientate all’utente.

## Pull Request — Checklist
1. **Ambito chirurgico**: la PR deve essere piccola, mirata e senza side-effect non necessari.
2. **Log**: nessun `print()`. Logger strutturati presenti negli orchestratori e nei moduli chiave.
3. **Interattività**: solo negli orchestratori. I moduli non devono usare `input()`/`sys.exit()`.
4. **Preview Docker**: invocata *detached*; stop automatico all’uscita dell’orchestratore.
5. **Push GitHub**: eseguito da `github_utils.py` con `GITHUB_TOKEN`; branch da env. Niente token in chiaro in URL o log.
6. **Path-safety**: verifica `is_safe_subpath` per tutti i file generati/modificati.
7. **Slug**: validazione via regex in `path_utils.py`. Se la config è stata aggiornata, ricorda `clear_slug_regex_cache()`.
8. **Docs**: aggiorna pagine interessate (`architecture.md`, `developer_guide.md`, `user_guide.md`, policy), oltre al `README.md`.
9. **CHANGELOG**: aggiungi entry coerente (PATCH/MINOR/MAJOR).
10. **Test**: esegui almeno i comandi base
    - `py src/pre_onboarding.py --slug demo --non-interactive --dry-run`
    - `py src/onboarding_full.py --slug demo --no-drive --non-interactive`
    - Se Docker attivo: verifica che la preview parta *detached* e venga fermata automaticamente all’uscita.

## Stile dei commit
Usa prefissi brevi e chiari:
- `fix(...)`: correzioni di bug/robustezza — es. `fix(preview): run detached and stop at exit`
- `feat(...)`: nuove funzionalità **compatibili** — es. `feat(slug): add clear_slug_regex_cache()`
- `perf(...)`: ottimizzazioni interne — es. `perf(path): cache slug regex`
- `docs(...)`: aggiornamenti documentazione — es. `docs(architecture): reflect detached preview`
- `chore(...)`: manutenzione — es. `chore(ci): bump actions/setup-python`

## Codice di condotta
Rimani rispettoso, proattivo e orientato alla soluzione. Le discussioni tecniche vanno motivate con riferimenti al codice e alle policy del repo.

---

## Domande frequenti (FAQ)

**D: Posso chiedere all’utente conferme dal modulo?**  
R: No. Le conferme/prompt sono responsabilità degli orchestratori. I moduli devono essere “batch-safe”.

**D: Cosa succede se Docker non è installato?**  
R: In `--non-interactive`, la preview viene **saltata automaticamente**. In interattivo, l’orchestratore chiede se proseguire senza anteprima.

**D: Dove scrivo i log?**  
R: Nel file unico del cliente `output/timmy-kb-<slug>/logs/onboarding.log`, utilizzando il logger strutturato.
