# 12. Env Override Capabilities (Beta 1.0)

Questo documento definisce la **SSoT** degli override via variabili d'ambiente
ammessi nel runtime Beta 1.0. Qualsiasi override **non elencato qui** e da
considerarsi non supportato e quindi **non consentito** nel runtime operativo.

Regole generali:
- override espliciti, deterministici e auditabili;
- nessun fallback implicito: valori invalidi devono generare stop deterministici;
- gli override non sostituiscono la configurazione di base (config/config.yaml).

Nota: credenziali e segreti (es. OPENAI_API_KEY, SERVICE_ACCOUNT_FILE, DRIVE_ID)
non sono "override": sono prerequisiti di esecuzione e non rientrano in questo elenco.

---

## A) Gating (UI capabilities)

- `DRIVE` -> 0/false/off/no disabilita i flussi Drive; default = disponibilita servizi.
- `VISION` -> 0/false/off/no disabilita il provisioning Vision; default = disponibilita servizi.
- `TAGS` -> 0/false/off/no disabilita tagging/Semantica; default = disponibilita servizi.

---

## B) Paths / Workspace

- `REPO_ROOT_DIR` -> override della root repo. Deve contenere `.git` o `pyproject.toml`.
- `WORKSPACE_ROOT_DIR` -> override della root workspace; puo includere `<slug>`.
  - In strict mode (`TIMMY_BETA_STRICT=1`) è obbligatorio che il valore risolva direttamente a
    `.../output/timmy-kb-<slug>`: impostare solo `.../output` senza lo slug porta
    a `ConfigError(code=workspace.root.invalid)` e blocca l'esecuzione.

Precedenza: `REPO_ROOT_DIR` ha precedenza su `WORKSPACE_ROOT_DIR` quando valido.

---

## C) Storage / Registry

- `CLIENTS_DB_PATH` -> path relativo sotto `clients_db/` (alias compatto).
- `CLIENTS_DB_DIR` / `CLIENTS_DB_FILE` -> override separati, sempre relativi a `clients_db/`.
- `ALLOW_CLIENTS_DB_IN_CLIENT` -> consente eccezionalmente il registry in workspace cliente.

Vincolo: nessun path assoluto o con `..`; se non valido -> ConfigError.

---

## D) Preview Stub / Preview runtime

- `PREVIEW_MODE=stub` -> abilita modalita stub della preview (nessun Docker).
- `PREVIEW_LOG_DIR` -> directory log per lo stub (deve esistere ed essere scrivibile).
- `PREVIEW_PORT` -> porta host per la preview (int; default 4000).
- `PREVIEW_READY_TIMEOUT` -> timeout readiness preview (secondi; default 30).

---

## Responsabilita operative

- UI e CLI devono trattare questi override come capability esplicite e tracciabili.
- Qualsiasi nuovo override richiede aggiornamento di questo documento.
