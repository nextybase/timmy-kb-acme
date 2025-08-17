# src/pipeline/context.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml
import sys
import shutil
import logging  # ⬅️ per tipizzare il logger

from .exceptions import ConfigError
from .env_utils import get_env_var
from .path_utils import is_valid_slug

# Rimosso l'import globale di get_structured_logger per evitare import circolari.
# Il logger viene risolto lazy quando serve (vedi _get_logger()).
logger: Optional[logging.Logger] = None


def get_or_prompt(
    value: Optional[str],
    prompt: str,
    non_interactive: bool = False,
    slug: Optional[str] = None,
) -> str:
    """Restituisce `value` se presente, altrimenti gestisce l’input in modo UX-safe.

    Comportamento:
    - **Interattivo**: chiede input all’utente tramite `input(prompt)`.
    - **Non interattivo**: solleva `ConfigError` esplicitando il parametro mancante.

    Args:
        value: Valore già disponibile (se truthy viene restituito).
        prompt: Messaggio da mostrare in caso di input interattivo.
        non_interactive: Se `True`, nessun prompt; errore se `value` assente.
        slug: Slug cliente da includere nel payload dell’eccezione.

    Returns:
        Il valore definitivo (esistente o inserito dall’utente).

    Raises:
        ConfigError: quando `non_interactive=True` e `value` è assente.
    """
    if value:
        return value
    if non_interactive:
        raise ConfigError(f"Parametro mancante: {prompt}", slug=slug)
    return input(prompt)


def validate_slug(slug: str) -> str:
    """Valida lo slug rispetto alle regole di progetto (fonte: `path_utils.is_valid_slug`).

    Args:
        slug: Identificativo cliente da validare.

    Returns:
        Lo slug originale se valido.

    Raises:
        ConfigError: se lo slug non rispetta la regex configurata.
    """
    if not is_valid_slug(slug):
        raise ConfigError(f"Slug '{slug}' non valido secondo le regole configurate.", slug=slug)
    return slug


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
    - Il modulo **non** interagisce con l’utente, salvo nei casi in cui il metodo `load()` venga
      invocato in modalità interattiva per rientrare in un flusso guidato (prompt di correzione slug).
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
    logger: Optional[logging.Logger] = None  # ⬅️ nuovo campo

    @classmethod
    def load(
        cls,
        slug: str,
        logger: Optional[logging.Logger] = None,
        interactive: Optional[bool] = None,
        **kwargs: Any,
    ) -> "ClientContext":
        """Carica (o inizializza) il contesto cliente e valida la configurazione.

        Comportamento:
        - Se la struttura cliente non esiste, viene creata e viene copiato un `config.yaml` di template.
        - In modalità interattiva consente correzione dello slug non valido via prompt.
        - Raccoglie variabili critiche dall’ambiente e costruisce i path canonici.

        Args:
            slug: Identificativo cliente da caricare/inizializzare.
            logger: Logger pre-esistente (riusato); se assente, viene creato lazy.
            interactive: `True` per abilitare prompt; `False` per batch; `None` → auto-detect.

        Returns:
            ClientContext popolato con path, config e logger.

        Raises:
            ConfigError: se slug invalido (in batch), se `config.yaml`/template mancano
                o in caso di errori di lettura della configurazione.
        """
        from .logging_utils import get_structured_logger  # import locale per evitare ciclico import

        # Rileva modalità interattiva
        if interactive is None:
            interactive = sys.stdin.isatty()

        # Logger strutturato (una sola istanza)
        _logger = logger or get_structured_logger(__name__)

        # Validazione slug
        if not is_valid_slug(slug):
            if interactive:
                _logger.warning(f"Slug non valido: '{slug}'. Deve contenere solo caratteri ammessi.")
                slug = input("📌 Reinserisci lo slug cliente: ").strip()
                slug = validate_slug(slug)
            else:
                raise ConfigError(f"Invalid slug format: '{slug}'", slug=slug)

        base_dir = Path(__file__).resolve().parents[2] / "output" / f"timmy-kb-{slug}"
        config_path = base_dir / "config" / "config.yaml"

        # 📦 Creazione automatica per nuovo cliente
        if not config_path.exists():
            _logger.info(f"Cliente '{slug}' non trovato: creazione struttura base.")
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

        _logger.info(f"Config cliente caricata: {config_path}")

        # Variabili da .env
        env_vars: Dict[str, Any] = {
            "SERVICE_ACCOUNT_FILE": get_env_var("SERVICE_ACCOUNT_FILE", required=True),
            "DRIVE_ID": get_env_var("DRIVE_ID", required=True),
            "GITHUB_TOKEN": get_env_var("GITHUB_TOKEN", default=None),
        }

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
            logger=_logger,  # ⬅️ iniettiamo il logger nel contesto
        )

    # -- Utility per tracking stato --

    def _get_logger(self) -> logging.Logger:
        """Ritorna il logger del contesto; se assente lo crea in modo lazy e coerente."""
        if self.logger:
            return self.logger
        # Fallback: creare un logger compat, evitando import ciclici
        from .logging_utils import get_structured_logger
        self.logger = get_structured_logger(__name__)
        return self.logger

    def log_error(self, msg: str) -> None:
        """Aggiunge un errore al tracking e lo registra nel logger."""
        log = self._get_logger()
        self.error_list.append(msg)
        log.error(msg)

    def log_warning(self, msg: str) -> None:
        """Aggiunge un warning al tracking e lo registra nel logger."""
        log = self._get_logger()
        self.warning_list.append(msg)
        log.warning(msg)

    def set_step_status(self, step: str, status: str) -> None:
        """Registra lo stato di uno step della pipeline (es. 'download' → 'done')."""
        log = self._get_logger()
        self.step_status[step] = status
        log.info(f"Step '{step}' → {status}")

    def summary(self) -> Dict[str, Any]:
        """Restituisce un riassunto sintetico dello stato corrente del contesto."""
        return {
            "slug": self.slug,
            "error_count": len(self.error_list),
            "warning_count": len(self.warning_list),
            "steps": self.step_status,
        }
