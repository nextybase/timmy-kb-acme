Agency & Orchestration Model - v1.0

Role Hierarchy
Timmy / ProtoTimmy - unico orchestratore globale e dialogico.
Domain Gatekeepers - categoria di agenti specializzati per dominio.
Engineering Gatekeeper (OCP) - istanza Dev/Prompt Governance della categoria Domain Gatekeepers che opera attraverso il Control Plane.
Micro-agents - esecutori puri sotto Work Order Envelope.
Timmy / ProtoTimmy
Agency decisionale globale: decide sequenza di prompt, seleziona Domain Gatekeepers, mantiene stato del dialogo con l'utente e gestisce escalation HiTL.
Conserva stato cognitivo: raccoglie intenti, genera prompt da inoltrare ai Domain Gatekeepers e redige message_for_ocp.
Non esegue codice né valida artefatti tecnici: delega tutto ai micro-agents tramite i Domain Gatekeepers; non interagisce direttamente con pipeline o file system.
Gestisce escalation / HiTL: attiva HiTL ogni volta che riceve stop_code == "HITL_REQUIRED" o quando la catena richiede intervento umano (tag approval, Skeptic/Entrypoint Gate).
Domain Gatekeepers (Category)
Categoria agenti per dominio: Domain Gatekeepers rappresentano la classe di agenti che portano conoscenza specialistica (Semantic, Compliance, Data, Engineering).
Funzioni: consulenza, validazione artefatti, blocco e correzione; possono coordinare micro-agents del dominio.
Conoscenza specifica: policy, AGENTS, schemi semantici, telemetria e guardrail del dominio di responsabilità.
Blocchi/escalation: Domain Gatekeepers possono bloccare la catena quando le policy SSoT vengono violate, quando file sensibili (e.g. semantic_mapping.yaml, tags.db) risultano non conformi, o quando i gate (Skeptic/Entrypoint) indicano un stop.
HiTL: possono richiedere HiTL (message_for_ocp, _CODEX_HITL_KEY, _should_proceed) e devono scalare a Timmy quando il valore decisionale supera l'ambito del dominio.
Non hanno agency globale né parlano con l'utente: comunicano solo con Timmy e micro-agents; non eseguono comandi autonomamente.
OCP as Domain Gatekeeper (Engineering)
Control Plane (Orchestration & Control Plane) è un layer operativo: non è un agente cognitivo, non decide, non esegue codice; è il canale attraverso cui transitano comandi, prompt e risultati.
Engineering Gatekeeper (OCP role) è un'istanza della categoria Domain Gatekeepers con competenze Dev/Prompt Governance.
OCP opera attraverso il Control Plane: applica decisioni prese da Timmy e dai Domain Gatekeepers, trasporta i prompt verso Codex/micro-agents, e riporta risultati verso Timmy.
OCP non è il Control Plane: il Control Plane è il layer (insieme di tools e procedure) che implementa i gate (Skeptic Gate, Entrypoint Guard); l'Engineering Gatekeeper è l'attore specialistico che agisce attraverso quel layer.
OCP applica decisioni: valida i prompt, verifica guardrail e attiva HiTL, ma non prende decisioni epistemiche a livello globale.
Micro-agents (Executors)
Esecutori puri: operano solo quando Timmy e i Domain Gatekeepers (via OCP) li incaricano; non prendono iniziativa né interpretano intenti.
Zero authority epistemica: non possiedono conoscenza decisionale del dominio; il loro compito è eseguire in modo tracciabile e dichiarato.
Contratto (Work Order Envelope): ogni esecuzione deve rispettare l'envelope, dichiarare side effect e restituire uno degli output ammessi (OK, NEED_INPUT, CONTRACT_ERROR).
Side effects: ammessi solo se esplicitamente richiesti; devono essere dichiarati e tracciati nei log (structured logging).
Codex è un micro-agent: riceve prompt da OCP attraverso il control plane e invia indietro strutturati risultati senza agire autonomamente.
Interaction Flow
Utente ↔ Timmy: ProtoTimmy riceve intenti e decide il dominio coinvolto.
Timmy → Domain Gatekeeper: prompt strutturato (via OCP) contenente politiche e artefatti.
Domain Gatekeeper → Micro-agent (via OCP/Codex): Gatekeeper trasmette il Work Order Envelope per esecuzione.
Micro-agent → Domain Gatekeeper: micro-agent restituisce StructuredResult (OK/NEED_INPUT/CONTRACT_ERROR).
Domain Gatekeeper → Timmy: riporta stato, evidenze, HiTL flag.
Timmy → Utente: aggiorna lo stato finale e notifica eventuale HiTL.
Chi NON parla direttamente: Domain Gatekeepers non comunicano con l'utente; micro-agents non decidono o interpretano intenti; Timmy non invia prompt direttamente ai micro-agents senza Gatekeeper.
Decisioni: prese da Timmy e Domain Gatekeepers.
Esecuzioni: affidate ai micro-agents (Codex).
STOP/escalation: avvengono nei Domain Gatekeepers (HiTL, gating procedures), il Control Plane applica lo stop.

Escalation & HiTL
STOP tecnico: CONTRACT_ERROR, ConfigError, PipelineError intercettati durante esecuzione.
STOP semantico: invalid mapping (semantic_mapping non conforme), invalid tags (semantic/tags_validation_failed), checkpoint _should_proceed.
STOP governance: Skeptic Gate e Entrypoint Guard bloccano l'operazione e richiedono ack documentato.
Escalazioni: Domain Gatekeepers scalano a Timmy quando policy contraddette o HiTL richiesto; Timmy scala all'utente quando riceve stop_code o message_for_ocp con HiTL flag.
Errori:
Tecnico: fallimenti runtime (exit code).
Semantico: invalidazione dati semantici.
Governance: guard procedure che richiedono documentazione (SKEPTIC_ACK.md, .codex/USER_DEV_SEPARATION.md).
Anti-Confusion Rules
Domain Gatekeepers ≠ Micro-agents: la categoria Gatekeeper valida e guida, i micro-agents eseguono.
"Gate" è un atto: Skeptic Gate, Entrypoint Guard, HiTL Gate sono procedure/fermate, non attori dotati di agency.
Control Plane ≠ Gatekeeper: Control Plane (OCP) è il livello operativo che trasporta prompt e applica decisioni; Engineering Gatekeeper è l'istanza Domain Gatekeeper che opera attraverso il Control Plane.
Timmy è l'unica agency globale: è l'unico soggetto a prendere decisioni orchestrative e dialogiche; gli altri ruoli sono subordinati e non globali.
Summary Table
Category / Instance	Decide	Validate	Execute
Timmy / ProtoTimmy (Global Orchestrator)	prompt sequence, HiTL escalation, gate assignment	enforces SSoT via Active Rules	none (delegates to micro-agents)
Domain Gatekeepers (Semantic, Compliance, Data, OCP role)	domain-specific block/escalate decisions	validate artifacts/logs/gates, trigger HiTL	do not execute code
Engineering Gatekeeper (OCP role)	applies decisions via Control Plane	enforces guardrails, OTA prompts	orchestrates micro-agent invocation
Micro-agents (Codex)	none	none (return structured status)	execute commands (OK/NEED_INPUT/CONTRACT_ERROR)
COMPLETE - READY FOR SSoT FREEZE
