# AGENT  Fine Tuning (UI)

> Nota: le **policy comuni** vivono in `docs/AGENTS_INDEX.md`. Questo file contiene **solo** gli override per l'area di fine-tuning UI e rimanda all'indice per tutto il resto. :contentReference[oaicite:5]{index=5}

## Scopo
- Fornire un **pannello UI** per ispezionare un Assistant OpenAI predefinito: lettura del **system prompt** e cattura dell**output grezzo** delle chiamate, **prima** di qualunque post-processing locale.
- Consentire la **revisione controllata** dei settaggi essenziali (modello, temperature/top-p, istruzioni, tool abilitati) e generare **micro-PR** mirati quando occorrono modifiche permanenti. :contentReference[oaicite:6]{index=6}

## Flusso vincolante
1. **Lettura**: recupera *id*, modello e **system prompt** dellAssistant tramite client wrapper; visualizza in modal **read-only** con pulsanti *Copia* e *(opz.) Esporta in file locale*.
2. **Prova**: esegue una richiesta *dry-run* con input minimi; mostra **l'output grezzo** dell'assistente senza arricchimenti o filtri (contratto E2E).
3. **Revisione**: permette ledit dei campi configurabili (istruzioni, temperature/top-p, tool); **nessuna scrittura remota** fino a esplicito *Conferma e aggiorna Assistant*.
4. **Persistenza locale**: eventuali esport/backup salvano solo nel workspace e **con I/O atomico**. Vietati side-effects a import-time. :contentReference[oaicite:7]{index=7} :contentReference[oaicite:8]{index=8}

## Regole (override)
- **HiTL e micro-PR**: le modifiche strutturali allAssistant si propongono come patch piccole, motivazione chiara, diff esplicito. :contentReference[oaicite:9]{index=9}
- **Path-safety & I/O**: ogni read/write passa da utility SSoT (`ensure_within*`, `safe_write_text/bytes`). Scrivere solo nel perimetro del workspace cliente. :contentReference[oaicite:10]{index=10}
- **No duplicazione policy**: qui solo regole/deroghe di ambito UI fine-tuning; rimandi all'indice per build/test/lint. :contentReference[oaicite:11]{index=11}
- **Modalita operative**: preferire scenario *Agent* (repo-aware) rispetto a *Full Access*; *Full Access* solo per task espliciti su branch dedicati. :contentReference[oaicite:12]{index=12}
- **Logging strutturato**: usa il logger centralizzato con `extra` coerenti (es. `slug`, `file_path`, `scope`).

## Criteri di accettazione
- Il modal **System Prompt** mostra *assistant_id*, *model*, **istruzioni complete** e tasto *Copia*; il dry-run espone **l'output grezzo** non alterato.
- Ogni write locale e **atomica** e confinata nel workspace; **nessuna** write fuori perimetro. :contentReference[oaicite:14]{index=14}
- Le modifiche remote allAssistant avvengono **solo** dopo conferma utente; in assenza di conferma, resta una proposta (diff/PR) coerente con le regole di indice. :contentReference[oaicite:15]{index=15}

## Riferimenti
- **Indice AGENT (SSoT policy)**: `docs/AGENTS_INDEX.md` (matrix & regole comuni). :contentReference[oaicite:16]{index=16}
- **Integrazione Codex & matrice**: uso agent-first, aggiornamento matrice con `pre-commit run agents-matrix-check --all-files`. :contentReference[oaicite:17]{index=17} :contentReference[oaicite:18]{index=18}
- **Safety/I/O atomico**: helper SSoT e convenzioni di test. :contentReference[oaicite:19]{index=19}
