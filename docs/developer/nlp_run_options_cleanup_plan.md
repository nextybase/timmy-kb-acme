# NLP Run Options Cleanup Plan (run_nlp_to_db)

Stato: pianificato (fase transitoria attiva con compatibilita legacy)
Scope: `timmy_kb.cli.tag_onboarding.run_nlp_to_db`

## Obiettivo
Rimuovere in modo controllato i parametri legacy:
- `rebuild`
- `only_missing`
- `max_workers`
- `worker_batch_size`
- `enable_entities`

e mantenere solo:
- `options: NlpRunOptions`

## Regola di precedenza corrente (transitoria)
- `options` è il contratto typed canonico.
- Se un parametro legacy è valorizzato (`!= None`), sovrascrive `options`.
- L'uso dei parametri legacy emette evento:
  - `cli.tag_onboarding.nlp_legacy_kwargs_deprecated`

## Piano di migrazione
1. Fase T0 (attuale):
- compatibilità backward attiva
- evento deprecazione attivo
- test di precedence attivi

2. Fase T1 (hardening prima dello switch):
- monitorare l'evento `cli.tag_onboarding.nlp_legacy_kwargs_deprecated`
- verificare assenza di punti di chiamata interni legacy
- aggiornare documentazione utenti/CLI indicando `options` come unico contratto supportato in release successiva

3. Fase T2 (switch):
- rimuovere parametri legacy dalla signature
- mantenere solo `options: NlpRunOptions`
- aggiornare tutti i punti di chiamata e i test

4. Fase T3 (post-switch):
- rimuovere logica di merge precedence legacy
- rimuovere evento deprecazione legacy
- mantenere test di regressione su API typed

## Checklist tecnica (T2)
- [ ] Modificare signature di `run_nlp_to_db` eliminando parametri legacy.
- [ ] Eliminare blocco `legacy_overrides` e relativo warning di deprecazione.
- [ ] Aggiornare punti di chiamata CLI in `main(...)` (gia su `NlpRunOptions`, verificare invarianti).
- [ ] Aggiornare eventuali punti di chiamata in test e tooling.
- [ ] Eseguire `pre-commit run --all-files`.
- [ ] Eseguire `python -m pytest -q`.

## Test di rimozione (da applicare in T2)
1. API typed only:
- chiamata con `options=NlpRunOptions(...)` deve funzionare senza warning legacy.

2. Parametri legacy rimossi:
- chiamata con `rebuild=...` (o altri legacy) deve fallire con `TypeError` per parametro inatteso.

3. Nessuna traccia evento legacy:
- `cli.tag_onboarding.nlp_legacy_kwargs_deprecated` non deve più essere emesso.

4. Compatibilita comportamento:
- stessi valori operativi (`rebuild`, `only_missing`, workers, batch, entities) passati via `options` devono produrre esito invariato rispetto al baseline pre-switch.

## Note di rischio
- Rischio principale: punti di chiamata esterni al repo che usano parametri legacy.
- Mitigazione: mantenere una release completa con deprecazione osservabile prima dello switch.
