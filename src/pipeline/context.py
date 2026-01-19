# SPDX-License-Identifier: GPL-3.0-only
# src/pipeline/context.py
"""ClientContext - contenitore unico di stato e configurazione per Timmy-KB.

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
  percorso canonico (`repo_root_dir`), impostazioni, logger e flag runtime.
- Fornisce utility di tracking e correlazione (`log_error`, `log_warning`,
  `set_step_status`, `summary`, `with_stage`, `with_run_id`).

Linee guida rispettate:
- **No I/O interattivo** e **no sys.exit**: gli orchestratori gestiscono UX e
  termination.
- **Path-safety STRONG**: i path scritti vengono verificati con `ensure_within(...)`.
- **SSoT** per le scritture: quando si crea il config iniziale si usa
  `safe_write_text` (atomica).
- **Determinismo**: `repo_root_dir` è l'unico punto di verità per il workspace.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, TypedDict, runtime_checkable

from .constants import SEMANTIC_DIR_NAME, SEMANTIC_MAPPING_FILE
from .env_utils import compute_redact_flag, get_bool, get_env_var
from .exceptions import ConfigError, InvalidSlug
from .file_utils import safe_write_text
from .logging_utils import get_structured_logger
from .path_utils import ensure_within, ensure_within_and_resolve
from .path_utils import validate_slug as _validate_slug
from .settings import Settings


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


@runtime_checkable
class SupportsGetItem(Protocol):
    def __getitem__(self, key: str) -> Any: ...

    def get(self, key: str, default: Any | None = None) -> Any: ...


class ClientSettingsDict(TypedDict, total=False):
    client_name: str
    slug: str
    ops_log_level: str


def _safe_settings_get(settings: Any | None, key: str) -> Any:
    """Estrae un valore da settings (dict/oggetto) senza assumere .get presente."""
    if settings is None:
        return None
    if isinstance(settings, dict):
        return settings.get(key)
    if isinstance(settings, SupportsGetItem):
        try:
            return settings.get(key)
        except Exception:
            try:
                return settings[key]
            except Exception:
                return None
    getter = getattr(settings, "get", None)
    if callable(getter):
        try:
            return getter(key)
        except Exception:
            return None
    return getattr(settings, key, None)


@dataclass(slots=True)
class ClientContext:
    """Contesto unificato per le pipeline Timmy-KB.

    Contiene:
    - Identità cliente (`slug`, `client_name`);
    - Percorso radice del workspace cliente **canonico** (`repo_root_dir`);
    - Configurazione YAML caricata (in `settings`) e path di riferimento
      (`config_path`, `mapping_path`);
    - Variabili d'ambiente risolte da `.env`/processo (`env`);
    - Flag runtime e strutture di tracking (`error_list`, `warning_list`, `step_status`);
    - Logger strutturato **iniettato** e riutilizzato (no print).

    Note di architettura:
    - Nessun input utente qui; gli orchestratori gestiscono UX.
    - La policy di redazione log è calcolata da `compute_redact_flag(...)`.
    - `stage` è un'etichetta opzionale della fase corrente (es. "scan_raw", "build_md").
    """

    # Identità cliente
    slug: str
    client_name: Optional[str] = None

    # === Path canonici ===
    repo_root_dir: Path | None = None  # single source of truth

    # Configurazione e path
    settings: Settings | Dict[str, Any] = field(default_factory=dict)
    config_path: Optional[Path] = None
    config_dir: Optional[Path] = None
    mapping_path: Optional[Path] = None

    # Risorse esterne (da .env)
    env: Dict[str, Any] = field(default_factory=dict)

    # Flag esecuzione
    no_interactive: bool = False
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
        # 0) Logger (unico) - includiamo run_id se presente
        _logger = cls._init_logger(logger, run_id)

        # 1) Validazione slug
        validate_slug(slug)

        # 2) Carica ENV (prima dei path per eventuale override)
        env_vars = cls._load_env(require_env=require_env)

        # 3) Calcola repo_root_dir (SSoT) con possibile override da kwargs/ENV
        repo_root_override = kwargs.get("repo_root_dir")
        repo_root = cls._compute_repo_root_dir(slug, env_vars, _logger, repo_root_override)

        # 4) Path & bootstrap minima (crea config se non presente) sotto repo_root_dir
        config_path = cls._ensure_config(repo_root, slug, _logger)

        # 5) Carica config cliente (yaml)
        # Config YAML e' SSoT non-segreto; i segreti restano in .env.
        settings = cls._load_yaml_config(repo_root, config_path, slug, _logger)

        # 6) Livello log (default dal config, override opzionale da kwargs)
        log_level_name = _coerce_log_level_name(getattr(settings, "ops_log_level", "INFO"))
        if "log_level" in kwargs:
            log_level_name = _coerce_log_level_name(kwargs["log_level"])
        log_level_value = _log_level_to_int(log_level_name)
        cls._apply_logger_level(_logger, log_level_value)

        # 7) Calcola redazione log
        redact = compute_redact_flag(env_vars, log_level_name)

        semantic_dir = ensure_within_and_resolve(repo_root, repo_root / SEMANTIC_DIR_NAME)

        return cls(
            slug=slug,
            client_name=_safe_settings_get(settings, "client_name"),
            repo_root_dir=repo_root,
            settings=settings,
            env=env_vars,
            config_path=config_path,
            config_dir=config_path.parent,
            # FIX SSoT: path reale e validato
            mapping_path=ensure_within_and_resolve(semantic_dir, semantic_dir / SEMANTIC_MAPPING_FILE),
            logger=_logger,
            run_id=run_id,
            stage=stage,
            log_level=log_level_name,
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
    def _apply_logger_level(logger: logging.Logger, level: int) -> None:
        """Aggiorna il livello del logger e degli handler esistenti."""
        try:
            logger.setLevel(level)
        except Exception:
            return
        for handler in list(getattr(logger, "handlers", []) or []):
            try:
                handler.setLevel(level)
            except Exception:
                continue

    @staticmethod
    def _compute_repo_root_dir(
        slug: str,
        env_vars: Dict[str, Any],
        logger: logging.Logger,
        repo_root_override: Path | str | None = None,
    ) -> Path:
        """Determina la root del workspace cliente.

        Priorità:
        - ENV `REPO_ROOT_DIR` (espansa e risolta).
        - Parametro `repo_root_dir` passato in `ClientContext.load(...)`.
        """
        if repo_root_override:
            try:
                root = Path(str(repo_root_override)).expanduser().resolve()
            except Exception as e:
                raise ConfigError(f"repo_root_dir non valido: {repo_root_override}", slug=slug) from e
            logger.info(
                "context.repo_root_dir_override",
                extra={"slug": slug, "repo_root_dir": str(root)},
            )
            return root

        env_root = env_vars.get("REPO_ROOT_DIR")
        if env_root:
            try:
                root = Path(str(env_root)).expanduser().resolve()
                repo_root = Path(__file__).resolve().parents[2]
                if root == repo_root:
                    # Ignoriamo l'override se punta alla radice repo, per evitare workspace
                    # creati direttamente nella repo stessa (fallimento UI).
                    env_root = None
                else:
                    expected = f"timmy-kb-{slug}"
                    if root.name.startswith("timmy-kb-") and root.name != expected:
                        root = root.parent / expected
                    logger.info(
                        "context.repo_root_dir_env",
                        extra={"slug": slug, "repo_root_dir": str(root)},
                    )
                    return root
            except Exception as e:
                raise ConfigError(f"REPO_ROOT_DIR non valido: {env_root}", slug=slug) from e

        raise ConfigError(
            "REPO_ROOT_DIR mancante: specifica un workspace root canonico.",
            slug=slug,
        )

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
                "context.config.bootstrap",
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
    def _load_yaml_config(repo_root: Path, config_path: Path, slug: str, logger: logging.Logger) -> Settings:
        """Carica e valida il file YAML di configurazione del cliente."""
        try:
            settings = Settings.load(repo_root, config_path=config_path, logger=logger, slug=slug)
            try:
                logger.info(
                    "context.config.loaded",
                    extra={"slug": slug, "file_path": str(config_path)},
                )
            except Exception:
                pass
            return settings
        except ConfigError:
            raise
        except Exception as e:  # pragma: no cover
            raise ConfigError(f"Errore lettura config cliente: {e}", file_path=config_path, slug=slug) from e

    @staticmethod
    def _load_env(*, require_env: bool) -> Dict[str, Any]:
        """Raccoglie variabili d'ambiente rilevanti (richieste/opzionali).

        Nota: qui si legge, non si redige; la policy di redazione è calcolata da
        `compute_redact_flag`.
        """
        env_vars: Dict[str, Any] = {}

        # Richieste (se require_env=True): mappare mancanze in ConfigError chiaro (no KeyError propagati)
        if require_env:
            missing: list[str] = []
            saf = get_env_var("SERVICE_ACCOUNT_FILE", default=None)
            did = get_env_var("DRIVE_ID", default=None)
            if not (saf and str(saf).strip()):
                missing.append("SERVICE_ACCOUNT_FILE")
            if not (did and str(did).strip()):
                missing.append("DRIVE_ID")
            if missing:
                from .exceptions import ConfigError  # import locale per evitare effetti collaterali

                raise ConfigError("Variabili d'ambiente mancanti o vuote: " + ", ".join(missing))
            env_vars["SERVICE_ACCOUNT_FILE"] = saf
            env_vars["DRIVE_ID"] = did
        else:
            env_vars["SERVICE_ACCOUNT_FILE"] = get_env_var("SERVICE_ACCOUNT_FILE", default=None)
            env_vars["DRIVE_ID"] = get_env_var("DRIVE_ID", default=None)

        # Opzionali utili
        env_vars["DRIVE_PARENT_FOLDER_ID"] = get_env_var("DRIVE_PARENT_FOLDER_ID", default=None)
        env_vars["LOG_REDACTION"] = get_env_var("LOG_REDACTION", default=None)
        env_vars["ENV"] = get_env_var("ENV", default=None)
        env_vars["CI"] = get_env_var("CI", default=None)
        env_vars["VISION_SAVE_SNAPSHOT"] = get_env_var("VISION_SAVE_SNAPSHOT", default=None)
        # NEW: override del root repo (sposta output altrove)
        env_vars["REPO_ROOT_DIR"] = get_env_var("REPO_ROOT_DIR", default=None)

        # Versione booleana di CI per chiamanti legacy
        env_vars["_CI_BOOL"] = get_bool("CI", default=False)
        env_vars["_VISION_SAVE_SNAPSHOT_BOOL"] = get_bool("VISION_SAVE_SNAPSHOT", default=True)

        return env_vars

    # -------------------------- Utility per tracking stato --------------------------

    def _get_logger(self) -> logging.Logger:
        """Ritorna il logger del contesto; se assente lo crea in modo lazy e coerente."""
        if self.logger:
            return self.logger
        self.logger = get_structured_logger(
            __name__,
            context=self,
            run_id=self.run_id,
            level=_log_level_to_int(self.log_level),
        )
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
            "context.step.status",
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


def _coerce_log_level(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        level_name = value.strip().upper()
        level = getattr(logging, level_name, None)
        if isinstance(level, int):
            return level
    try:
        return int(value)
    except Exception:
        return logging.INFO


def _coerce_log_level_name(value: Any) -> str:
    if isinstance(value, str):
        name = value.strip().upper()
        return name if name else "INFO"
    try:
        numeric = int(value)
        return logging.getLevelName(numeric) if isinstance(logging.getLevelName(numeric), str) else "INFO"
    except Exception:
        return "INFO"


def _log_level_to_int(value: str) -> int:
    level = getattr(logging, value.upper(), None)
    if isinstance(level, int):
        return level
    return logging.INFO
