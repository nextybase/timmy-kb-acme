# Coding Rules — Timmy‑KB (v1.0.4)

Regole operative per scrivere e manutenere il codice della pipeline. Obiettivo: stabilità, tracciabilità, sicurezza e comportamento deterministico in batch.

---

## 1) Linguaggio, stile, tipizzazione
- Python ≥ 3.10. Usa type hints ovunque nelle API pubbliche; `dataclasses` quando chiariscono il modello.
- Docstring brevi (stile Google) con esempi solo quando servono.
- Naming: `snake_case` per funzioni/variabili, `UPPER_CASE` per costanti, classi in `PascalCase`.
- Ordine degli import: stdlib → terze parti → locali; preferisci import **assoluti**.
- Strumenti consigliati: Ruff, Black, Mypy, pre‑commit.

---

## 2) Orchestratori vs Moduli
- Orchestratori: gestiscono UX/CLI (prompt, conferme), selezione modalità (`--non-interactive`, `--dry-run`, `--no-drive`, `--push|--no-push`), mapping eccezioni → `EXIT_CODES`, avvio/stop preview Docker e policy di redazione log.
- Moduli: eseguono azioni tecniche e sono batch‑safe. **Vietati** `input()` e `sys.exit()`; niente prompt.
- Output umano leggibile solo negli orchestratori; i moduli espongono dati e/o eccezioni tipizzate.

---

## 3) Logging ed errori
- Niente `print()`. Usa `logging_utils.get_structured_logger(name, log_file=?, context=?, run_id=?, extra_base=?, rotate=?)`.
- Includi metadati utili (`slug`, `file_path`, `step`, …) via `extra={...}`.
- Non loggare segreti. Se previsto, abilita la **redazione** tramite policy degli orchestratori e usa i punti di log che supportano `redact_logs`.
- Solleva solo eccezioni della tassonomia in `exceptions.py` (es. `ConfigError`, `PreviewError`, `DriveDownloadError`, `PushError`). Evita `except Exception` generici.
- Gli orchestratori mappano le eccezioni a `EXIT_CODES` in modo deterministico.

---

## 4) I/O, sicurezza e atomicità
- Usa `pathlib.Path` ovunque; encoding `utf-8`.
- Verifica i percorsi con `is_safe_subpath` prima di operare fuori dalla sandbox del cliente.
- Scritture **atomiche** per file critici (tmp + replace). Evita side‑effect non necessari.
- Non serializzare credenziali o token su disco; nessun segreto in chiaro nei log.

---

## 5) Configurazioni e cache
- YAML solo con `yaml.safe_load`; fallback sicuri per chiavi mancanti.
- La regex dello **slug** è letta da `config/config.yaml` ed è **messa in cache**; se una modifica tocca tale configurazione, invoca la funzione di **clear** della cache subito dopo.
- Le variabili d’ambiente si leggono tramite `env_utils` (getter centralizzati, con default/required espliciti). Evita accessi diretti a `os.environ` sparsi.

---

## 6) Subprocess, Docker, GitHub
- `subprocess.run([...], check=True)`; non usare `shell=True` salvo reale necessità e con sanitizzazione.
- Preview HonKit: dal modulo si esegue **build/serve** senza prompt; invocazione **detached** per default; lo **stop** è responsabilità degli orchestratori.
- Push GitHub: centralizzato in `github_utils.py`. Token obbligatorio e validazione precoce; branch da `GIT_DEFAULT_BRANCH` (fallback `main`). Non esporre PAT in log/URL.

---

## 7) Drive e rete
- Retry esponenziale con jitter e **tetto temporale** sul backoff cumulato per chiamate esterne.
- Download idempotente: skip se MD5/size coincidono; preserva la gerarchia remota in locale.
- Metriche leggere di retry e backoff loggate a fine operazione; propaga un riepilogo anche nel contesto quando disponibile.
- Abilita `redact_logs` dove supportato per evitare leakage di path o identificativi sensibili.

---

## 8) Deprecation & compat
- Mantieni alias deprecati per almeno una **MINOR** dopo l’avviso (es. `--skip-push` → `--no-push`) con warning esplicito.
- Evita breaking changes nelle firme dei moduli richiamati dagli orchestratori; se inevitabili, versione **MAJOR** con guida di migrazione.

---

## 9) Test minimi (manuali)
- Pre‑onboarding (setup locale, nessun servizio):
  `py src/pre_onboarding.py --slug demo --non-interactive --dry-run`
- Onboarding (senza Drive, senza push):
  `py src/onboarding_full.py --slug demo --no-drive --non-interactive`
- Onboarding con Docker attivo: verifica che la preview parta **detached** e che lo **stop** avvenga **automaticamente** in uscita.
- Push in batch:
  `GITHUB_TOKEN=... GIT_DEFAULT_BRANCH=main py src/onboarding_full.py --slug demo --no-drive --non-interactive --push`

---

## 10) Qualità del codice
- Funzioni piccole, una responsabilità per volta.
- Privilegia chiarezza e manutenibilità; ottimizzazioni solo misurate e localizzate.
- Commenti sintetici e pertinenti; niente rumorosità.

---

### Esempi rapidi
**Logger corretto in un modulo**
```python
from pipeline.logging_utils import get_structured_logger
logger = get_structured_logger("pipeline.content_utils")

def do_work(context, file):
    logger.info(
        "Operazione completata",
        extra={"slug": context.slug, "file_path": str(file)}
    )
```

**Errore tipizzato + mapping orchestratore**
```python
# modulo
from pipeline.exceptions import PreviewError

def preview(context, *args, **kwargs):
    raise PreviewError("Build fallita", slug=context.slug)

# orchestratore
import sys
from pipeline.exceptions import EXIT_CODES, PreviewError
try:
    preview(context, ...)
except PreviewError:
    sys.exit(EXIT_CODES["PreviewError"])
```

