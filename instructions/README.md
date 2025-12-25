Cos’è `instructions/`
- Design-first specification repository per il control plane ProtoTimmy.
- NON è documentazione descrittiva; è un deposito di contratti operativi.
- NON è implementazione; esegue solo precise definizioni di ruoli, fasi, gate e artifact.
- Ogni file definisce contratti verificabili, non opinioni soggettive.

Obiettivo finale (Definition of Done)
- Interazione utente fatta esclusivamente tramite ProtoTimmy.
- ProtoTimmy orchestra Domain Gatekeepers e micro-agent con coverage e HiTL conformi.
- OCP (Engineering Gatekeeper) dirige Codex/micro-agent attraverso il Control Plane.
- Prompt Chain completa, lineare e governata, con transizioni di fase e failure mode espliciti.
- Pipeline dati estesa fino alla trasformazione definitiva dei markdown operativi.

Regole non negoziabili
- Ogni documento produce artefatti verificabili (stati, file, log, stop_code) come prove dell’esecuzione.
- Separazione netta tra WHAT (contratti, invarianti, failure modes) e HOW (codice futuro).
- Nessuna ambiguità su chi decide (Timmy), chi valida (Domain Gatekeepers/OCP) e chi esegue (micro-agent).
- Ogni fallback, errore e stop viene esplicitato nel documento con owner, trigger e resume_rule.

Elenco dei documenti previsti (stato)
- `00_ssot_agency.md` (congelato)
- `01_intents_and_actions.md` (attivo, in raffinamento)
- `02_prompt_chain_lifecycle.md` (attivo)
- `09_context_layout_contract_beta.md` (congelato)
- `03_gatekeepers_contracts.md` (DA SCRIVERE)
- `04_microagents_work_orders.md` (DA SCRIVERE)
- `05_pipeline_state_machine.md` (DA SCRIVERE)
- `06_ui_contract.md` (DA SCRIVERE)

Come lavorare sui documenti
- Eseguire un micro-planning verbale prima di scrivere o modificare qualsiasi file.
- Allineare ogni modifica alla terminologia e alla struttura dei documenti esistenti (Timmy/ProtoTimmy, Domain Gatekeepers, Control Plane, micro-agent, message_for_ocp legacy).
- Evitare nuove terminologie non allineate; preferire tabelle, checklist, invarianti, failure modes.
- Scrivere in tono normativo; mantenere bullet brevi e frasi operative.

Avvertenza finale
- Questo README è temporaneo e verrà rimosso una volta completata la specifica.
- Serve solo a guidare Codex e il processo di progettazione durante la fase di definizione.
