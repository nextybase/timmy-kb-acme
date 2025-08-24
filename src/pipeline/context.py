# src/pipeline/context.py
"""
Definizione del `ClientContext`, il contenitore unificato di stato e configurazione
per le pipeline Timmy-KB.

Funzioni principali:
- Gestione delle identità cliente (`slug`, `client_name`) e dei percorsi canonici locali.
- Introduzione di `repo_root_dir` come single source of truth per i path (compatibile
  con i campi storici `base_dir`, `output_dir`, ecc.).
- Caricamento e validazione della configurazione YAML del cliente.
- Risoluzione delle variabili d’ambiente e propagazione del flag di redazione log
  tramite `compute_redact_flag`.
- Tracking dello stato di esecuzione (errori, warning, step completati) con logger
  strutturato.

Aggiornamenti:
- (NEW) `repo_root_dir` permette override via variabile d’ambiente `REPO_ROOT_DIR`.
- (NEW) `stage` opzionale per etichettare la fase corrente di pipeline.
- I fallback di path restano per retro-compatibilità, ma tutti derivano da `repo_root_dir`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import yaml
import shutil
import logging  # per tipizzare/gestire il logger

from .exceptions import ConfigError, InvalidSlug
from .env_utils import get_env_var, get_bool, compute_redact_flag
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
    - Percorso radice del repo cliente **canonico** (`repo_root_dir`) e derivati locali (`raw_dir`, `md_dir`, `log_dir`, ...);
    - Configurazione YAML caricata (in `settings`) e path di riferimento (`config_path`, `mapping_path`);
    - Variabili d’ambiente risolte da `.env`/processo (`env`);
    - Flag runtime e strutture di tracking (`error_list`, `warning_list`, `step_status`);
    - Logger strutturato **iniettato** e riutilizzato (niente print).

    Note di architettura:
    - Il modulo **non** interagisce con l’utente. Eventuali input/loop sono responsabilità degli orchestratori.
    - La **policy di redazione log** è centralizzata e calcolata via `compute_redact_flag(...)` in `env_utils.py`.
    - (NEW, non-breaking) `repo_root_dir` è il punto di verità dei path; i campi storici (`base_dir`, `output_dir`, ...) restano per compatibilità.
    - (NEW, opzionale) `stage`: etichetta per la fase corrente (es. "scan_raw", "build_md").
    """

    # Identità cliente
    slug: str
    client_name: Optional[str] = None

    # === Path canonici ===
    repo_root_dir: Path | None = None  # NEW: single source of truth

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

    # Fase corrente (NEW, opzionale)
    stage: Optional[str] = None

    # Toggle redazione log (calcolato in load())
    redact_logs: bool = False

    # =============================== Caricamento/inizializzazione ===============================

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
        """Carica (o inizializza) il contesto cliente e valida la configurazione.

        Comportamento:
        - Se la struttura cliente non esiste, viene creata e bootstrap del `config.yaml` da template.
        - Raccoglie variabili critiche dall’ambiente e costruisce i path canonici.
        - Calcola il flag `redact_logs` tramite `compute_redact_flag(...)`.
        """
        # 0) Logger (unico) – includiamo run_id se presente
        _logger = cls._init_logger(logger, run_id)

        # 🔕 Deprecation notice soft: loggato una sola volta se il parametro viene usato
        if interactive is not None:
            _logger.debug(
                "Parametro 'interactive' è deprecato e viene ignorato; gestire l'I/O utente negli orchestratori.",
                extra={"slug": slug},
            )

        # 1) Validazione slug (triggera anche cache regex in path_utils, se applicabile)
        validate_slug(slug)

        # 2) Carica env risolto (richiesto/opzionale) – PRIMA dei path per poter applicare override
        env_vars = cls._load_env(require_env=require_env)

        # 3) Calcola repo_root_dir (SST) con possibile override da ENV; fallback deterministico
        repo_root = cls._compute_repo_root_dir(slug, env_vars, _logger)

        # 4) Path & bootstrap minima (crea config se non presente) sotto repo_root_dir
        config_path = cls._ensure_config(repo_root, slug, _logger)

        # 5) Carica config cliente (yaml)
        settings = cls._load_yaml_config(config_path, _logger)

        # 6) Livello log (default INFO; se passato via kwargs mantiene retro-compatibilità)
        log_level = str(kwargs.get("log_level", "INFO")).upper()

        # 7) Calcola redazione log (policy centralizzata) – NO side effects
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

    # =============================== Helper interni (Fase 1) ===============================

    @staticmethod
    def _init_logger(logger: Optional[logging.Logger], run_id: Optional[str]) -> logging.Logger:
        """Istanzia (o riusa) il logger strutturato dell'applicazione."""
        if logger is not None:
            return logger
        from .logging_utils import get_structured_logger  # import locale per evitare ciclico import
        return get_structured_logger(__name__, run_id=run_id)

    @staticmethod
    def _compute_repo_root_dir(slug: str, env_vars: Dict[str, Any], logger: logging.Logger) -> Path:
        """Determina il repo_root_dir:
        - Se `REPO_ROOT_DIR` è definita nell'ambiente → usa quella (espansa/risolta);
        - Altrimenti fallback deterministico alla struttura locale `output/timmy-kb-<slug>` sotto il progetto."""
        # ENV override (può puntare direttamente alla root del cliente)
        env_root = env_vars.get("REPO_ROOT_DIR")
        if env_root:
            try:
                root = Path(str(env_root)).expanduser().resolve()
                logger.info("repo_root_dir impostato da ENV", extra={"repo_root_dir": str(root)})
                return root
            except Exception as e:
                raise ConfigError(f"REPO_ROOT_DIR non valido: {env_root} ({e})")

        # Fallback deterministico (vecchio comportamento)
        # NOTE: __file__/parents[2] → radice progetto; mantenuto per compatibilità
        default_root = Path(__file__).resolve().parents[2] / "output" / f"timmy-kb-{slug}"
        return default_root

    @staticmethod
    def _ensure_config(repo_root_dir: Path, slug: str, logger: logging.Logger) -> Path:
        """Assicura la presenza di `config/config.yaml` sotto `repo_root_dir`, creando struttura da template se assente."""
        config_path = repo_root_dir / "config" / "config.yaml"
        if not config_path.exists():
            logger.info(
                "Cliente '%s' non trovato: creazione struttura base.", slug,
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
        return config_path

    @staticmethod
    def _load_yaml_config(config_path: Path, logger: logging.Logger) -> Dict[str, Any]:
        """Carica il file YAML di configurazione del cliente."""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                settings = yaml.safe_load(f) or {}
        except Exception as e:  # pragma: no cover
            raise ConfigError(f"Errore lettura config cliente: {e}", file_path=config_path) from e

        logger.info("Config cliente caricata: %s", config_path, extra={"file_path": str(config_path)})
        return settings

    @staticmethod
    def _load_env(*, require_env: bool) -> Dict[str, Any]:
        """Raccoglie variabili d'ambiente rilevanti (richieste/opzionali).

        Nota: si limita a leggere i valori; la policy di redazione è calcolata da `compute_redact_flag`.
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
        # NEW: override del root repo (se serve spostare output altrove)
        env_vars["REPO_ROOT_DIR"] = get_env_var("REPO_ROOT_DIR", default=None)

        # Conserviamo anche una versione booleana di CI per possibili chiamanti legacy
        env_vars["_CI_BOOL"] = get_bool("CI", default=False)

        return env_vars

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
        log.info("Step '%s' → %s", step, status, extra={"slug": self.slug, "step": step, "status": status})

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
