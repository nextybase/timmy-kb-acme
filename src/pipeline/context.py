# src/pipeline/context.py
"""ClientContext – contenitore unico di stato e configurazione per Timmy-KB.

Che cosa fa questo modulo (overview):
- Valida lo slug cliente (`validate_slug`).
- Calcola la radice canonica del workspace cliente (`_compute_repo_root_dir`),
  con override da ENV `REPO_ROOT_DIR`.
- Garantisce la presenza del `config/config.yaml` del cliente (`_ensure_config`),
  generandolo da template se mancante.
- Carica la configurazione YAML del cliente (`_load_yaml_config`).
- Raccoglie le variabili d'ambiente necessarie/opzionali (`_load_env`) e calcola
  la policy di redazione log (in `env_utils`).
- Espone il dataclass `ClientContext.load(...)` che costruisce in modo coerente
  percorsi canonici (repo_root_dir, raw_dir, md_dir, log_dir, …), impostazioni,
  logger e flag runtime.
- Fornisce utility di tracking e correlazione (`log_error`, `log_warning`,
  `set_step_status`, `summary`, `with_stage`, `with_run_id`).

Linee guida rispettate:
- **No I/O interattivo** e **no sys.exit**: gli orchestratori gestiscono UX e
  termination.
- **Path-safety STRONG**: i path scritti vengono verificati con `ensure_within(...)`.
- **SSoT** per le scritture: quando si crea il config iniziale si usa
  `safe_write_text` (atomica).
- **Compatibilità**: i campi storici (`base_dir`, `output_dir`, ecc.) restano ma
  derivano da `repo_root_dir`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env_utils import compute_redact_flag, get_bool, get_env_var
from .exceptions import ConfigError, InvalidSlug
from .file_utils import safe_write_text
from .logging_utils import get_structured_logger
from .path_utils import ensure_within
from .path_utils import validate_slug as _validate_slug


def validate_slug(slug: str) -> str:
    """Valida lo slug delegando a `path_utils.validate_slug` e mappando l'errore.

    Args:
        slug: Identificativo cliente da validare.

    Returns:
        Lo slug originale se valido.

    Raises:
        ConfigError: se lo slug non rispetta la regex configurata.
    """
    try:
        return _validate_slug(slug)
    except InvalidSlug as e:
        # Mappa l'eccezione di dominio in ConfigError per coerenza con la pipeline
        raise ConfigError(str(e), slug=slug) from e


@dataclass
class ClientContext:
    """Contesto unificato per le pipeline Timmy-KB.

    Contiene:
    - Identità cliente (`slug`, `client_name`);
    - Percorso radice del workspace cliente **canonico** (`repo_root_dir`) e derivati locali
      (`raw_dir`, `md_dir`, `log_dir`, ...);
    - Configurazione YAML caricata (in `settings`) e path di riferimento
      (`config_path`, `mapping_path`);
    - Variabili d’ambiente risolte da `.env`/processo (`env`);
    - Flag runtime e strutture di tracking (`error_list`, `warning_list`, `step_status`);
    - Logger strutturato **iniettato** e riutilizzato (no print).

    Note di architettura:
    - Nessun input utente qui; gli orchestratori gestiscono UX.
    - La policy di redazione log è calcolata da `compute_redact_flag(...)`.
    - `repo_root_dir` è il punto di verità dei path; i campi storici restano per compat.
    - `stage` è un’etichetta opzionale della fase corrente (es. "scan_raw", "build_md").
    """

    # Identità cliente
    slug: str
    client_name: Optional[str] = None

    # === Path canonici ===
    repo_root_dir: Path | None = None  # single source of truth

    # Configurazione e path
    settings: Dict[str, Any] = field(default_factory=dict)
    config_path: Optional[Path] = None
    config_dir: Optional[Path] = None
    mapping_path: Optional[Path] = None

    # Campi storici (compat) – derivati da repo_root_dir
    base_dir: Optional[Path] = None
    output_dir: Optional[Path] = None
    raw_dir: Optional[Path] = None
    md_dir: Optional[Path] = None
    log_dir: Optional[Path] = None

    # Risorse esterne (da .env)
    env: Dict[str, Any] = field(default_factory=dict)

    # Flag esecuzione
    no_interactive: bool = False
    auto_push: bool = False
    skip_preview: bool = False
    log_level: str = "INFO"
    dry_run: bool = False

    # Stato runtime
    error_list: List[str] = field(default_factory=list)
    warning_list: List[str] = field(default_factory=list)
    step_status: Dict[str, str] = field(default_factory=dict)

    # Logger (iniettato una sola volta)
    logger: Optional[logging.Logger] = None  # teniamo il riferimento (nessun print)

    # Correlazione run
    run_id: Optional[str] = None

    # Fase corrente (opzionale)
    stage: Optional[str] = None

    # Toggle redazione log (calcolato in load())
    redact_logs: bool = False

    # ============================ Caricamento / init ============================

    @classmethod
    def load(
        cls,
        slug: str,
        logger: Optional[logging.Logger] = None,
        interactive: Optional[bool] = None,  # compat, ignorato
        *,
        require_env: bool = True,
        run_id: Optional[str] = None,
        stage: Optional[str] = None,
        **kwargs: Any,
    ) -> "ClientContext":
        """Carica/inizializza il contesto cliente e valida configurazione + ambiente.

        Pipeline di caricamento:
          1) Valida `slug`.
          2) Carica ENV (richiesto/opzionale) → override `REPO_ROOT_DIR` se presente.
          3) Determina `repo_root_dir` e garantisce la presenza di `config/config.yaml`
             (bootstrap se mancante).
          4) Carica impostazioni dal YAML.
          5) Calcola `redact_logs` (policy centralizzata).
        """
        # 0) Logger (unico) – includiamo run_id se presente
        _logger = cls._init_logger(logger, run_id)

        # Deprecation notice soft (parametro non più usato qui)
        if interactive is not None:
            _logger.debug(
                ("Parametro 'interactive' è deprecato e viene ignorato; " "gestire l'I/O utente negli orchestratori."),
                extra={"slug": slug},
            )

        # 1) Validazione slug
        validate_slug(slug)

        # 2) Carica ENV (prima dei path per eventuale override)
        env_vars = cls._load_env(require_env=require_env)

        # 3) Calcola repo_root_dir (SST) con possibile override da ENV
        repo_root = cls._compute_repo_root_dir(slug, env_vars, _logger)

        # 4) Path & bootstrap minima (crea config se non presente) sotto repo_root_dir
        config_path = cls._ensure_config(repo_root, slug, _logger)

        # 5) Carica config cliente (yaml)
        settings = cls._load_yaml_config(config_path, _logger)

        # 6) Livello log (default INFO; retro-compat da kwargs)
        log_level = str(kwargs.get("log_level", "INFO")).upper()

        # 7) Calcola redazione log
        redact = compute_redact_flag(env_vars, log_level)

        return cls(
            slug=slug,
            client_name=(settings or {}).get("client_name"),
            repo_root_dir=repo_root,
            settings=settings or {},
            env=env_vars,
            config_path=config_path,
            config_dir=config_path.parent,
            mapping_path=(config_path.parent / "semantic_mapping.yaml"),
            # Campi storici (compat) – derivati dal root canonico
            base_dir=repo_root,
            output_dir=repo_root,
            raw_dir=repo_root / "raw",
            md_dir=repo_root / "book",
            log_dir=repo_root / "logs",
            logger=_logger,
            run_id=run_id,
            stage=stage,
            log_level=log_level,
            redact_logs=redact,
        )

    # =============================== Helper interni ===============================

    @staticmethod
    def _init_logger(logger: Optional[logging.Logger], run_id: Optional[str]) -> logging.Logger:
        """Istanzia (o riusa) il logger strutturato dell'applicazione."""
        if logger is not None:
            return logger
        return get_structured_logger(__name__, run_id=run_id)

    @staticmethod
    def _compute_repo_root_dir(slug: str, env_vars: Dict[str, Any], logger: logging.Logger) -> Path:
        """Determina la root del workspace cliente.

        Priorità:
        - ENV `REPO_ROOT_DIR` (espansa e risolta).
        - Fallback deterministico: `<project_root>/output/timmy-kb-<slug>`.
        """
        env_root = env_vars.get("REPO_ROOT_DIR")
        if env_root:
            try:
                root = Path(str(env_root)).expanduser().resolve()
                logger.info("repo_root_dir impostato da ENV", extra={"repo_root_dir": str(root)})
                return root
            except Exception as e:
                raise ConfigError(f"REPO_ROOT_DIR non valido: {env_root} ({e})") from e

        # Project root = this file → ../../
        default_root = Path(__file__).resolve().parents[2] / "output" / f"timmy-kb-{slug}"
        return default_root

    @staticmethod
    def _ensure_config(repo_root_dir: Path, slug: str, logger: logging.Logger) -> Path:
        """Assicura la presenza di `config/config.yaml` sotto `repo_root_dir`.

        Se assente, crea la struttura da template.

        Sicurezza:
        - Verifica path con `ensure_within` prima della scrittura.
        - Scrittura atomica tramite `safe_write_text`.
        - Template risolto rispetto alla **radice progetto**.
        """
        config_dir = repo_root_dir / "config"
        config_path = config_dir / "config.yaml"

        # Path-safety (perimetro = repo_root_dir)
        config_dir.mkdir(parents=True, exist_ok=True)
        ensure_within(repo_root_dir, config_dir)
        ensure_within(repo_root_dir, config_path)

        if not config_path.exists():
            logger.info(
                "Cliente '%s' non trovato: creazione struttura base.",
                slug,
                extra={"slug": slug, "file_path": str(config_path)},
            )
            # Template dal progetto
            template_config = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
            if not template_config.exists():
                raise ConfigError(
                    f"Template config.yaml globale non trovato: {template_config}",
                    slug=slug,
                    file_path=template_config,
                )
            # Copia sicura (atomica) del contenuto (path-safety anche in LETTURA)
            from .path_utils import read_text_safe

            payload = read_text_safe(template_config.parent, template_config, encoding="utf-8")
            safe_write_text(config_path, payload, encoding="utf-8", atomic=True)

        return config_path

    @staticmethod
    def _load_yaml_config(config_path: Path, logger: logging.Logger) -> Dict[str, Any]:
        """Carica e valida il file YAML di configurazione del cliente."""
        try:
            from .yaml_utils import yaml_read

            settings = yaml_read(config_path.parent, config_path) or {}
        except Exception as e:  # pragma: no cover
            raise ConfigError(f"Errore lettura config cliente: {e}", file_path=config_path) from e

        logger.info("Config cliente caricata", extra={"file_path": str(config_path)})
        return settings

    @staticmethod
    def _load_env(*, require_env: bool) -> Dict[str, Any]:
        """Raccoglie variabili d'ambiente rilevanti (richieste/opzionali).

        Nota: qui si legge, non si redige; la policy di redazione è calcolata da
        `compute_redact_flag`.
        """
        env_vars: Dict[str, Any] = {}

        # Richieste (se require_env=True)
        if require_env:
            env_vars["SERVICE_ACCOUNT_FILE"] = get_env_var("SERVICE_ACCOUNT_FILE", required=True)
            env_vars["DRIVE_ID"] = get_env_var("DRIVE_ID", required=True)
        else:
            env_vars["SERVICE_ACCOUNT_FILE"] = get_env_var("SERVICE_ACCOUNT_FILE", default=None)
            env_vars["DRIVE_ID"] = get_env_var("DRIVE_ID", default=None)

        # Opzionali utili
        env_vars["DRIVE_PARENT_FOLDER_ID"] = get_env_var("DRIVE_PARENT_FOLDER_ID", default=None)
        env_vars["GITHUB_TOKEN"] = get_env_var("GITHUB_TOKEN", default=None)
        env_vars["LOG_REDACTION"] = get_env_var("LOG_REDACTION", default=None)
        env_vars["ENV"] = get_env_var("ENV", default=None)
        env_vars["CI"] = get_env_var("CI", default=None)
        # NEW: override del root repo (sposta output altrove)
        env_vars["REPO_ROOT_DIR"] = get_env_var("REPO_ROOT_DIR", default=None)

        # Versione booleana di CI per chiamanti legacy
        env_vars["_CI_BOOL"] = get_bool("CI", default=False)

        return env_vars

    # -------------------------- Utility per tracking stato --------------------------

    def _get_logger(self) -> logging.Logger:
        """Ritorna il logger del contesto; se assente lo crea in modo lazy e coerente."""
        if self.logger:
            return self.logger
        self.logger = get_structured_logger(__name__, context=self, run_id=self.run_id)
        return self.logger

    def log_error(self, msg: str) -> None:
        """Aggiunge un errore al tracking e lo registra nel logger."""
        log = self._get_logger()
        self.error_list.append(msg)
        log.error(msg, extra={"slug": self.slug})

    def log_warning(self, msg: str) -> None:
        """Aggiunge un warning al tracking e lo registra nel logger."""
        log = self._get_logger()
        self.warning_list.append(msg)
        log.warning(msg, extra={"slug": self.slug})

    def set_step_status(self, step: str, status: str) -> None:
        """Registra lo stato di uno step della pipeline.

        Esempio: `'download' → 'done'`.
        """
        log = self._get_logger()
        self.step_status[step] = status
        log.info(
            "Step '%s' → %s",
            step,
            status,
            extra={"slug": self.slug, "step": step, "status": status},
        )

    def summary(self) -> Dict[str, Any]:
        """Restituisce un riassunto sintetico dello stato corrente del contesto."""
        return {
            "slug": self.slug,
            "run_id": self.run_id,
            "stage": self.stage,
            "error_count": len(self.error_list),
            "warning_count": len(self.warning_list),
            "steps": self.step_status,
            "redact_logs": self.redact_logs,
            "repo_root_dir": str(self.repo_root_dir) if self.repo_root_dir else None,
        }

    # -------------------- Utility non-invasive per run_id / stage --------------------

    def with_stage(self, stage: Optional[str]) -> "ClientContext":
        """Ritorna una copia del contesto con `stage` aggiornato (immutability-friendly)."""
        return replace(self, stage=stage)

    def with_run_id(self, run_id: Optional[str]) -> "ClientContext":
        """Ritorna una copia del contesto con `run_id` aggiornato (immutability-friendly)."""
        return replace(self, run_id=run_id)

    # Alias legacy (se qualche chiamante li usasse già)
    def set_stage(self, stage: Optional[str]) -> "ClientContext":  # pragma: no cover
        return self.with_stage(stage)

    def set_run_id(self, run_id: Optional[str]) -> "ClientContext":  # pragma: no cover
        return self.with_run_id(run_id)
