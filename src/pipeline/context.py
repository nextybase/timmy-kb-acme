# src/pipeline/context.py

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml
from .exceptions import ConfigError


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

    # Risorse esterne
    drive_folders: Dict[str, str] = field(default_factory=dict)
    github_repo: Optional[str] = None

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
        Carica e valida la configurazione cliente, restituendo un ClientContext pronto all'uso.
        """
        # Import lazy per evitare circular import
        from pipeline.logging_utils import get_structured_logger

        base_dir = Path(__file__).resolve().parents[2]
        config_path = base_dir / "output" / f"timmy-kb-{slug}" / "config" / "config.yaml"

        if not config_path.exists():
            raise ConfigError(f"Config file non trovato per slug '{slug}'")

        with open(config_path, "r", encoding="utf-8") as f:
            settings = yaml.safe_load(f) or {}

        logger = get_structured_logger(__name__, context=cls(slug=slug))
        logger.info("Config cliente caricato", extra={"slug": slug, "config_path": str(config_path)})

        return cls(
            slug=slug,
            client_name=settings.get("client_name"),
            settings=settings,
            config_path=config_path,
            mapping_path=(config_path.parent / "semantic_mapping.yaml"),
            base_dir=base_dir,
            output_dir=base_dir / "output" / f"timmy-kb-{slug}",
            raw_dir=base_dir / "output" / f"timmy-kb-{slug}" / "raw",
            md_dir=base_dir / "output" / f"timmy-kb-{slug}" / "book",
            log_dir=base_dir / "output" / f"timmy-kb-{slug}" / "logs",
            drive_folders=settings.get("drive_folders", {}),
            github_repo=settings.get("github_repo", "")
        )

    # --- Utility per tracking stato ---
    def log_error(self, msg: str):
        from pipeline.logging_utils import get_structured_logger
        logger = get_structured_logger(__name__, context=self)
        self.error_list.append(msg)
        logger.error(msg, extra={"slug": self.slug})

    def log_warning(self, msg: str):
        from pipeline.logging_utils import get_structured_logger
        logger = get_structured_logger(__name__, context=self)
        self.warning_list.append(msg)
        logger.warning(msg, extra={"slug": self.slug})

    def set_step_status(self, step: str, status: str):
        from pipeline.logging_utils import get_structured_logger
        logger = get_structured_logger(__name__, context=self)
        self.step_status[step] = status
        logger.info(f"Step '{step}' → {status}", extra={"slug": self.slug})

    def summary(self) -> Dict[str, Any]:
        return {
            "slug": self.slug,
            "error_count": len(self.error_list),
            "warning_count": len(self.warning_list),
            "steps": self.step_status
        }
