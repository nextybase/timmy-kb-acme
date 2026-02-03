# Runbook Drive Provisioning (Beta)

Documentazione contrattuale per la pipeline deterministica di onboarding che separa nettamente bootstrap locale, Vision e provisioning Drive.

## Pipeline A/B/C (SSoT)

1. **Fase A - Workspace bootstrap locale + VisionStatement**
   - SSoT: `system/specs/workspace_layout.v1.yaml` guida la creazione di `raw/`, `normalized/`, `config/` e `semantic/`.
   - Output obbligatorio: `VisionStatement.yaml` (normalizzazione PDF -> YAML) senza alcun accesso a Drive.

2. **Fase B - Vision provision locale**
   - SSoT: `semantic/semantic_mapping.yaml` generato e validato localmente da `vision_provision`.
   - Nessuna operazione Drive: il file resta nel workspace e serve come sorgente per la fase C.

3. **Fase C - Provisioning Drive + publish README (manuale)**
   - Trigger esplicito dell'utente dalla UI "Genera struttura Drive".
   - Riceve la SSoT da `semantic_mapping.yaml` e da `system/specs/workspace_layout.v1.yaml` per costruire la struttura `raw/<area.key>` su Drive prima di pubblicare i README.
   - Drive e capability esplicita e non un prerequisito per Fase A/B; si attiva solo dopo il completamento locale delle fasi precedenti.

## Contratto: Genera struttura Drive (Given / When / Then)

**Given**
- Workspace locale valido con layout `workspace_layout.v1.yaml` applicato.
- `semantic/semantic_mapping.yaml` presente e coerente.
- Drive configurato (`SERVICE_ACCOUNT_FILE`, `DRIVE_ID`, extras `[drive]` installati).

**When**
- L'operatore clicca il bottone "Genera struttura Drive" nella pagina Gestisci (`src/ui/pages/manage.py`).

**Then** (eseguito in ordine deterministico, fail-fast sui prerequisiti)
1. Ensure della root cliente su Drive secondo la SSoT layout.
2. Ensure delle cartelle `raw/` e `config/` (spec-driven, senza scritture manuali).
3. Ensure di `raw/<area.key>` per ogni area prevista dallo SSoT (no fallback o shim).
4. Pubblica i README in Drive in modo idempotente.
- Fail-fast: qualsiasi prerequisito mancante causa errore esplicito.
- No update di registry/ownership, nessun path non previsto viene modificato.
- L'intera sequenza e deterministica, non introduce scaffold temporanei o shim.

## Out of Scope

- Non crea workspace locale (Fase A gia gestita altrove).
- Non genera VisionStatement ne semantic_mapping (Fase B).
- Non aggiorna `clients.yaml`, `clients_db` o ownership metadata.
- Non include logiche Drive automatiche o ambientazioni di permessi diversi.

## Error model (strict)

- **Errori ammessi**: `semantic_mapping` mancante o invalido, variabili Drive non configurate, permessi Drive negati, `ensure_within` che fallisce.
- **Comportamento**: il sistema fallisce fast, logga l'errore strutturato e non lascia warning silenti ne soft-recovery.
- **Niente soft-match**: non si mascherano permessi o parametri, tutto viene notificato come errore `ContractError` o `PipelineError`.
- Questo modello e vincolante per il core: nessun warning skip, nessun fallback "graceful" nel processo di publishing.
