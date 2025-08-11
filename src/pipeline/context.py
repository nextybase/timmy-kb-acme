from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml
import logging
import shutil

from .exceptions import ConfigError
from .env_utils import get_env_var  # importa per variabili da .env

# Logger semplice per uso interno
logger = logging.getLogger(__name__)

@dataclass
class ClientContext:
    """Contesto unificato per tutte le pipeline Timmy-KB."""

    # Identità cliente
    slug: str
    client_name: Optional[str] = None

    # Configurazione e path
    settings: Dict[str, Any] = field(default_factory=dict)
    config_path: Path = None
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
    def load(cls, slug: str) -> "ClientContext":
        """
        Carica e valida la configurazione cliente.
        Se la cartella/config non esiste, viene creata automaticamente.
        """
        base_dir = Path(__file__).resolve().parents[2] / "output" / f"timmy-kb-{slug}"
        config_path = base_dir / "config" / "config.yaml"

        # ✅ Creazione automatica per nuovo cliente
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

        logger.info(f"Config cliente caricato: {config_path}")

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
            mapping_path=(config_path.parent / "semantic_mapping.yaml"),
            base_dir=base_dir,
            output_dir=base_dir,
            raw_dir=base_dir / "raw",
            md_dir=base_dir / "book",
            log_dir=base_dir / "logs"
        )

    # -- Utility per tracking stato --
    def log_error(self, msg: str):
        self.error_list.append(msg)
        logger.error(msg)

    def log_warning(self, msg: str):
        self.warning_list.append(msg)
        logger.warning(msg)

    def set_step_status(self, step: str, status: str):
        self.step_status[step] = status
        logger.info(f"Step '{step}' → {status}")

    def summary(self) -> Dict[str, Any]:
        return {
            "slug": self.slug,
            "error_count": len(self.error_list),
            "warning_count": len(self.warning_list),
            "steps": self.step_status
        }
