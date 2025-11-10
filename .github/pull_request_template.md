## Scopo
<!-- breve descrizione -->

## Checklist
- [ ] Rispetto **Coding Rules** (typing, logger strutturato, **no `print()`**)  <!-- vedi CONTRIBUTING -->
- [ ] Path-safety & scritture **atomiche** dove si scrive su FS
- [ ] Doc aggiornate (README / docs/*) e CHANGELOG aggiornato se serve **(blocking)** — aggiungi in descrizione `Docs: ...`
- [ ] Test/coverage ok (pytest) e type-check ok (mypy)
- [ ] QA eseguito dal venv: `venv/Script(s)/python -m ruff|black|mypy` oppure attiva il venv e lancia `make qa-safe`
- [ ] Nessun push forzato, oppure `--force-with-lease` + allow-list + `force_ack`  <!-- governance push -->

## Docs
<!-- Elenca qui i file di documentazione aggiornati oppure scrivi `n/a` solo se non sono necessari update. -->
Docs:
