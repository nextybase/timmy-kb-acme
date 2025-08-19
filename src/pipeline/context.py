from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml
import shutil
import logging  # per tipizzare/gestire il logger

from .exceptions import ConfigError, InvalidSlug
from .env_utils import get_env_var, get_bool
from .path_utils import validate_slug as _validate_slug


def validate_slug(slug: str) -> str:
    """Valida lo slug delegando a `path_utils.validate_slug` e mappando l'errore di dominio.

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
        # Mappa l'eccezione di dominio in ConfigError per coerenza con il resto della pipeline
        raise ConfigError(str(e), slug=slug) from e


@dataclass
class ClientContext:
    """Contesto unificato per le pipeline Timmy-KB.

    Contiene:
    - Identità cliente (`slug`, `client_name`);
    - Percorsi locali canonici (`output_dir`, `raw_dir`, `md_dir`, `log_dir`, `config_dir`);
    - Configurazione YAML caricata (in `settings`) e path di riferimento (`config_path`, `mapping_path`);
    - Variabili d’ambiente risolte da `.env`/processo (`env`);
    - Flag runtime e strutture di tracking (`error_list`, `warning_list`, `step_status`);
    - Logger strutturato **iniettato** e riutilizzato (niente ricreazioni ad ogni chiamata).

    Nota di architettura:
    - Il modulo **non** interagisce con l’utente. Eventuali input/loop sono responsabilità degli orchestratori.
    - La **policy di redazione log** è centralizzata qui: campo `redact_logs` calcolato
      in base a variabili env e log_level.
    - (NEW, non-breaking) `stage`: etichetta opzionale per la fase corrente (es. "scan_raw", "build_md"),
      utile per correlare i log insieme a `run_id`.
    """

    # Identità cliente
    slug: str
    client_name: Optional[str] = None

    # Configurazione e path
    settings: Dict[str, Any] = field(default_factory=dict)
    config_path: Optional[Path] = None
    config_dir: Optional[Path] = None
    mapping_path: Optional[Path] = None
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

    # Fase corrente (NEW, opzionale)
    stage: Optional[str] = None

    # Toggle redazione log (calcolato in load())
    redact_logs: bool = False

    @classmethod
    def load(
        cls,
        slug: str,
        logger: Optional[logging.Logger] = None,
        interactive: Optional[bool] = None,  # mantenuto per compatibilità, ma ignorato
        *,
        require_env: bool = True,
        run_id: Optional[str] = None,
        stage: Optional[str] = None,
        **kwargs: Any,
    ) -> "ClientContext":
        """Carica (or inizializza) il contesto cliente e valida la configurazione.

        Comportamento:
        - Se la struttura cliente non esiste, viene creata e viene copiato un `config.yaml` di template.
        - Raccoglie variabili critiche dall’ambiente e costruisce i path canonici.
        - Calcola il flag `redact_logs` secondo la policy centralizzata (auto|on|off).

        Policy `LOG_REDACTION`:
        - `auto` (default): attiva redazione se ENV ∈ {prod, production, ci} oppure CI=true,
          oppure se sono presenti credenziali (GitHub o Service Account).
        - `on`: forza redazione sempre.
        - `off`: disattiva redazione sempre.
        - In ogni caso, se `log_level=DEBUG`, la redazione è **forzata OFF** (debug locale).
        """
        from .logging_utils import get_structured_logger  # import locale per evitare ciclico import

        # Logger strutturato (una sola istanza) — includiamo run_id se presente
        _logger = logger or get_structured_logger(__name__, run_id=run_id)

        # 🔕 Deprecation notice soft: loggato una sola volta se il parametro viene usato
        if interactive is not None:
            _logger.debug(
                "Parametro 'interactive' è deprecato e viene ignorato; "
                "gestire l'I/O utente negli orchestratori.",
                extra={"slug": slug},
            )

        # Validazione slug
        validate_slug(slug)

        base_dir = Path(__file__).resolve().parents[2] / "output" / f"timmy-kb-{slug}"
        config_path = base_dir / "config" / "config.yaml"

        # 📦 Creazione automatica per nuovo cliente
        if not config_path.exists():
            _logger.info(
                f"Cliente '{slug}' non trovato: creazione struttura base.",
                extra={"slug": slug, "file_path": str(config_path)},
            )
            config_path.parent.mkdir(parents=True, exist_ok=True)
            template_config = Path("config") / "config.yaml"
            if not template_config.exists():
                raise ConfigError(
                    f"Template config.yaml globale non trovato: {template_config}",
                    slug=slug,
                    file_path=template_config,
                )
            shutil.copy(template_config, config_path)

        # Lettura config
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                settings = yaml.safe_load(f)
        except Exception as e:
            raise ConfigError(f"Errore lettura config cliente: {e}", slug=slug, file_path=config_path)

        _logger.info(
            f"Config cliente caricata: {config_path}",
            extra={"slug": slug, "file_path": str(config_path)},
        )

        # Variabili da .env (condizionate da require_env)
        env_vars: Dict[str, Any] = {}
        if require_env:
            env_vars["SERVICE_ACCOUNT_FILE"] = get_env_var("SERVICE_ACCOUNT_FILE", required=True)
            env_vars["DRIVE_ID"] = get_env_var("DRIVE_ID", required=True)
        else:
            env_vars["SERVICE_ACCOUNT_FILE"] = get_env_var("SERVICE_ACCOUNT_FILE", default=None)
            env_vars["DRIVE_ID"] = get_env_var("DRIVE_ID", default=None)

        # Variabili opzionali utili
        env_vars["DRIVE_PARENT_FOLDER_ID"] = get_env_var("DRIVE_PARENT_FOLDER_ID", default=None)
        env_vars["GITHUB_TOKEN"] = get_env_var("GITHUB_TOKEN", default=None)
        env_vars["LOG_REDACTION"] = get_env_var("LOG_REDACTION", default=None)
        env_vars["ENV"] = get_env_var("ENV", default=None)
        env_vars["CI"] = get_env_var("CI", default=None)

        # --- Policy redazione log centralizzata ---
        log_level = str(kwargs.get("log_level", "INFO")).upper()
        debug_mode = (log_level == "DEBUG")

        mode_raw = env_vars.get("LOG_REDACTION") or get_env_var("LOG_REDACTION", default="auto")
        mode = str(mode_raw or "auto").strip().lower()

        env_name = (env_vars.get("ENV") or get_env_var("ENV", default="dev") or "dev").strip().lower()
        ci_flag = get_bool("CI", default=False) or str(env_vars.get("CI") or "").strip().lower() in {"1", "true", "yes", "on"}
        has_credentials = bool(env_vars.get("GITHUB_TOKEN") or env_vars.get("SERVICE_ACCOUNT_FILE"))

        if mode in {"always", "on"} or str(mode) in {"1", "true", "yes", "on"}:
            redact = True
        elif mode in {"never", "off"} or str(mode) in {"0", "false", "no"}:
            redact = False
        else:
            # auto
            redact = (env_name in {"prod", "production", "ci"}) or ci_flag or has_credentials

        if debug_mode:
            redact = False  # debug locale forza OFF

        return cls(
            slug=slug,
            client_name=(settings or {}).get("client_name"),
            settings=settings or {},
            env=env_vars,
            config_path=config_path,
            config_dir=config_path.parent,
            mapping_path=(config_path.parent / "semantic_mapping.yaml"),
            base_dir=base_dir,
            output_dir=base_dir,
            raw_dir=base_dir / "raw",
            md_dir=base_dir / "book",
            log_dir=base_dir / "logs",
            logger=_logger,
            run_id=run_id,
            stage=stage,
            log_level=log_level,
            redact_logs=redact,
        )

    # -- Utility per tracking stato --

    def _get_logger(self) -> logging.Logger:
        """Ritorna il logger del contesto; se assente lo crea in modo lazy e coerente."""
        if self.logger:
            return self.logger
        from .logging_utils import get_structured_logger  # import locale per evitare ciclico import
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
        """Registra lo stato di uno step della pipeline (es. 'download' → 'done')."""
        log = self._get_logger()
        self.step_status[step] = status
        log.info(f"Step '{step}' → {status}", extra={"slug": self.slug, "step": step, "status": status})

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
        }

    # -- Utility non-invasive per run_id/stage (NEW) --

    def with_stage(self, stage: Optional[str]) -> "ClientContext":
        """Ritorna una copia del contesto con `stage` aggiornato."""
        return replace(self, stage=stage)

    def with_run_id(self, run_id: Optional[str]) -> "ClientContext":
        """Ritorna una copia del contesto con `run_id` aggiornato."""
        return replace(self, run_id=run_id)

    # Alias legacy (se qualche chiamante li usasse già): manteniamo la semantica
    def set_stage(self, stage: Optional[str]) -> "ClientContext":  # pragma: no cover
        return self.with_stage(stage)

    def set_run_id(self, run_id: Optional[str]) -> "ClientContext":  # pragma: no cover
        return self.with_run_id(run_id)
