from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml
import sys
import shutil

from .exceptions import ConfigError
from .env_utils import get_env_var   # importa per variabili da .env
from .path_utils import is_valid_slug

# Rimosso l'import globale di get_structured_logger per evitare circular import
logger = None  # inizializzato in load()

@dataclass
class ClientContext:
    """Contesto unificato per tutte le pipeline Timmy-KB."""

    # Identità cliente
    slug: str
    client_name: Optional[str] = None

    # Configurazione e path
    settings: Dict[str, Any] = field(default_factory=dict)
    config_path: Path = None
    config_dir: Optional[Path] = None  # ✅ aggiunto per accesso diretto alla cartella di configurazione
    mapping_path: Optional[Path] = None
    base_dir: Path = None
    output_dir: Path = None
    raw_dir: Path = None
    md_dir: Path = None
    log_dir: Path = None

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

    @classmethod
    def load(cls, slug: str, logger=None, interactive=None):
        """
        Carica e valida la configurazione cliente.
        Se la cartella/config non esiste, viene creata automaticamente.
        """
        from .logging_utils import get_structured_logger  # import locale per evitare circular import

        # Rileva modalità interattiva
        if interactive is None:
            interactive = sys.stdin.isatty()

        # Logger strutturato di default
        logger = logger or get_structured_logger(__name__)

        # Validazione slug
        while not is_valid_slug(slug):
            if interactive:
                logger.warning(f"Slug non valido: '{slug}'. Deve contenere solo minuscole, numeri e trattini.")
                slug = input("🔐 Reinserisci lo slug cliente: ").strip()
            else:
                raise ConfigError(f"Invalid slug format: '{slug}'")

        base_dir = Path(__file__).resolve().parents[2] / "output" / f"timmy-kb-{slug}"
        config_path = base_dir / "config" / "config.yaml"

        # 📂 Creazione automatica per nuovo cliente
        if not config_path.exists():
            logger.info(f"Cliente '{slug}' non trovato: creazione struttura base.")
            config_path.parent.mkdir(parents=True, exist_ok=True)
            template_config = Path("config") / "config.yaml"
            if not template_config.exists():
                raise ConfigError(f"Template config.yaml globale non trovato: {template_config}")
            shutil.copy(template_config, config_path)

        # Lettura config
        with open(config_path, "r", encoding="utf-8") as f:
            settings = yaml.safe_load(f)

        logger.info(f"Config cliente caricata: {config_path}")

        # Carica variabili da .env
        env_vars = {
            "SERVICE_ACCOUNT_FILE": get_env_var("SERVICE_ACCOUNT_FILE", required=True),
            "DRIVE_ID": get_env_var("DRIVE_ID", required=True),
            "GITHUB_TOKEN": get_env_var("GITHUB_TOKEN", default=None)
        }

        return cls(
            slug=slug,
            client_name=settings.get("client_name"),
            settings=settings,
            env=env_vars,
            config_path=config_path,
            config_dir=config_path.parent,  # ✅ inizializzazione della nuova proprietà
            mapping_path=(config_path.parent / "semantic_mapping.yaml"),
            base_dir=base_dir,
            output_dir=base_dir,
            raw_dir=base_dir / "raw",
            md_dir=base_dir / "book",
            log_dir=base_dir / "logs"
        )

    # -- Utility per tracking stato --
    def log_error(self, msg: str):
        from .logging_utils import get_structured_logger
        log = get_structured_logger(__name__)
        self.error_list.append(msg)
        log.error(msg)

    def log_warning(self, msg: str):
        from .logging_utils import get_structured_logger
        log = get_structured_logger(__name__)
        self.warning_list.append(msg)
        log.warning(msg)

    def set_step_status(self, step: str, status: str):
        from .logging_utils import get_structured_logger
        log = get_structured_logger(__name__)
        self.step_status[step] = status
        log.info(f"Step '{step}' → {status}")

    def summary(self) -> Dict[str, Any]:
        return {
            "slug": self.slug,
            "error_count": len(self.error_list),
            "warning_count": len(self.warning_list),
            "steps": self.step_status
        }
