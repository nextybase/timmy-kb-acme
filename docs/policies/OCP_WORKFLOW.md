# OCP → Codex Workflow

1. **Scopo**: l’OCP traduce piani in Prompt numerati, Codex applica micro-PR con diff/report/QA, l’umano mantiene il merge gate e non esegue codice.
2. **Regola base**: `main` riceve modifiche solo via PR; vedere docs/security.md per richieste di branch protection (`CI`, `Secret Scan`, approval). Nessuna scrittura diretta su `main`.
3. **Mapping Prompt → Commit**:
   - Prompt 0: analisi read-only, nessun file modificato.
   - Prompt 1..N: ogni prompt genera un micro-PR mirato (1 diff, 1 report, `pytest -q -k "not slow"`).
   - Prompt N+1: finale con `pre-commit run --all-files` + `pytest -q`, riepilogo in italiano e commit conclusivo.
4. **Comandi standard**:
   - `pytest -q -k "not slow"` (intermedio su ogni prompt operativo).
   - `pre-commit run --all-files` e `pytest -q` al prompt finale.
5. **Regole NO**:
   - NO file fuori dallo scope dichiarato.
   - NO refactor non richiesti.
   - NO bypass degli hook o della QA; se fallano, correggere e ripetere fino a max 10 tentativi.
   - NO merge diretto su `main` senza autorizzazione OCP/Senior Reviewer.
6. **Checklist merge**:
   - QA intermedi eseguiti (`pytest -q -k "not slow"`).
   - QA finale completata (`pre-commit run --all-files`, `pytest -q`).
   - Skeptic Gate documentato (Evidence/Scope/Rischi/Decisione).
   - Note HiTL compilate (reviewer, domande aperte, verifiche rimaste).
7. **Flusso operativo**:
   - Codex applica la patch, produce diff/report/QA, e si ferma.
   - L’OCP valuta evidenze e alimenta lo Skeptic Gate; solo PASS libera il prompt successivo.
   - Il branch viene approvato e mergeato solo dopo tutti i checkpoints e con il commit finale redatto in italiano.
