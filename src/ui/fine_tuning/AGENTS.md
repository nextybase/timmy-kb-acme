# Scopo
Pannello UI per ispezionare un Assistant OpenAI (system prompt e output grezzo) e gestire in modo controllato settaggi e proposte di modifica.

# Regole (override)
- Flusso vincolante: lettura assistant (id, modello, system prompt) in modal read-only con copia/esporta; dry-run con output grezzo; revisione di campi configurabili senza write remota fino a conferma; eventuali export/backup solo nel workspace con I/O atomico.
- Modifiche all'Assistant proposte come micro-PR HiTL, con motivazione chiara e diff esplicito.
- Path-safety: ogni read/write passa da utility SSoT (`ensure_within*`, `safe_write_text/bytes`); scritture solo nel perimetro cliente.
- Modalita operativa: preferire scenario Agent; Full Access solo per task espliciti su branch dedicati.
- Logging strutturato con `extra` coerenti (es. `slug`, `file_path`, `scope`); nessun side-effect a import-time.

# Criteri di accettazione
- Il modal System Prompt mostra `assistant_id`, `model`, istruzioni complete e pulsante Copia; il dry-run espone l'output grezzo non alterato.
- Ogni write locale e atomica e confinata nel workspace; nessuna scrittura fuori perimetro.
- Le modifiche remote all'Assistant avvengono solo dopo conferma esplicita; in assenza, restano come proposta/micro-PR.

# Riferimenti
- docs/AGENTS_INDEX.md
