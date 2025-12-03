# Milestone  Stabilizzazione Script Archivio

## Obiettivo
Stabilizzare il repository dopo lo spostamento degli script legacy in `scripts/archive/` e verificarne l'assenza di dipendenze, in modo da poter eliminare definitivamente la cartella al termine della milestone.

Aggiornamento: la cartella `scripts/archive/` è stata rimossa (nessuna dipendenza residua). Mantenere il controllo periodico affinché non vengano reintrodotti script legacy fuori dai percorsi ufficiali.

## Scope
- Script attualmente archiviati:
  - `scripts/archive/__orig_manage.py`
  - `scripts/archive/assistants_smoke.py`
  - `scripts/archive/check_structure.py`
  - `scripts/archive/kb_healthcheck_responses.py`
  - `scripts/archive/quick_openai_diag.py`
  - `scripts/archive/refactor_logging_ui.py`
  - `scripts/archive/vision_alignment_check.py`
- Nessun cambiamento funzionale al flusso attivo (`onboarding_ui.py`, `timmy_kb_coder.py`, CLI pipeline).
- Validazione che non esistano riferimenti residui (import, make target, documentazione operativa).

## Attivita
1. **Monitoraggio build/CI**  assicurarsi che pre-commit e suite CI restino verdi per almeno due cicli completi.
2. **Verifica documentale**  confermare che README, Runbook e guide non richiedano piu gli script archiviati (in caso contrario aggiornare i riferimenti).
3. **Raccolta feedback team**  condividere l'elenco con i referenti di pipeline/UI e confermare che non vi siano piani di riuso.
4. **Decisione finale**  (completata): cartella `scripts/archive/` rimossa dopo verifica assenza dipendenze.

## Esito atteso
Alla chiusura della milestone la cartella `scripts/archive/` puo essere eliminata senza impatti, avendo garantito che lo storico sia stato preservato nelle PR e nella documentazione.
