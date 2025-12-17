# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

from ai.client_factory import make_openai_client
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.paths import get_repo_root
from pipeline.settings import Settings
from rosetta.logging_conventions import build_rosetta_event_extra, event_name
from semantic.contracts import AssertionContract, RelationContract


@dataclass(frozen=True, slots=True)
class RosettaConfig:
    enabled: bool = False
    provider: str = "openai"
    model: Optional[str] = None

    @classmethod
    def load(
        cls,
        *,
        settings: Settings | None = None,
        repo_root: Path | None = None,
    ) -> "RosettaConfig":
        settings_obj = settings or Settings.load(repo_root or get_repo_root())
        raw = settings_obj.get("rosetta", {}) or {}
        return cls(
            enabled=bool(raw.get("enabled", False)),
            provider=str(raw.get("provider", "openai")),
            model=raw.get("model"),
        )


def _mask_metadata(metadata: Optional[Mapping[str, Any]]) -> Mapping[str, str]:
    if not metadata:
        return {}
    return {str(key): type(value).__name__ for key, value in metadata.items()}


class RosettaClient(ABC):
    """Base client Rosetta; espone check/explain coerenti con KG e logging."""

    def __init__(self, *, slug: Optional[str] = None, model: Optional[str] = None):
        self._slug = slug
        self._model = model

    def _extra_ctx(
        self,
        *,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        extra: dict[str, Any] = {}
        if self._model:
            extra["model"] = self._model
        masked = _mask_metadata(metadata)
        if masked:
            extra["metadata_summary"] = masked
        return extra

    @abstractmethod
    def check_coherence(
        self,
        *,
        assertions: Iterable[AssertionContract],
        run_id: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Mapping[str, Any]:
        """Valuta coerenza su assertions tipizzate secondo il contratto KG."""
        ...

    @abstractmethod
    def propose_updates(
        self,
        *,
        assertion_id: str,
        candidate: Mapping[str, Any],
        provenance: Optional[Mapping[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> Mapping[str, Any]: ...

    @abstractmethod
    def explain(
        self,
        *,
        assertion_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        run_id: Optional[str] = None,
        relations: Optional[Iterable[RelationContract]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Mapping[str, Any]:
        """Fornisce riferimenti tracciabili (assertion_id, relation_id, run_id, trace_id)."""
        ...


class OpenAIRosettaClient(RosettaClient):
    def __init__(
        self,
        *,
        slug: Optional[str] = None,
        model: Optional[str] = None,
        client_factory: Callable[[], Any] | None = None,
    ):
        super().__init__(slug=slug, model=model)
        self._client_factory = client_factory or make_openai_client
        self._client: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                self._client = self._client_factory()
            except ConfigError:
                raise
            except Exception as exc:
                raise ConfigError(f"Impossibile costruire il client OpenAI per Rosetta: {exc}") from exc
        return self._client

    def _log(
        self,
        name: str,
        *,
        run_id: Optional[str],
        metadata: Optional[Mapping[str, Any]] = None,
        assertion_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        step_id: Optional[str] = None,
        artifact_id: Optional[str] = None,
        assertions_count: Optional[int] = None,
        metadata_fields_count: Optional[int] = None,
        candidate_fields_count: Optional[int] = None,
        provenance_fields_count: Optional[int] = None,
        extra: Optional[Mapping[str, Any]] = None,
    ):
        extra_ctx = build_rosetta_event_extra(
            event=event_name(name),
            slug=self._slug,
            run_id=run_id,
            step_id=step_id,
            artifact_id=artifact_id,
            assertion_id=assertion_id,
            trace_id=trace_id,
            assertions_count=assertions_count,
            metadata_fields_count=metadata_fields_count,
            candidate_fields_count=candidate_fields_count,
            provenance_fields_count=provenance_fields_count,
        )
        extra_ctx.update(self._extra_ctx(metadata=metadata))
        if extra:
            extra_ctx.update(extra)
        logger = get_structured_logger("rosetta")
        logger.info(extra_ctx["event"], extra=extra_ctx)

    def check_coherence(
        self,
        *,
        assertions: Iterable[Mapping[str, Any]],
        run_id: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Mapping[str, Any]:
        assertions_list = list(assertions)
        self._log(
            "check_coherence",
            run_id=run_id,
            metadata=metadata,
            assertions_count=len(assertions_list),
            metadata_fields_count=len(metadata) if metadata is not None else None,
        )
        self._ensure_client()
        return {"status": "ok", "summary": "Rosetta stub verifica coerenza", "details": []}

    def propose_updates(
        self,
        *,
        assertion_id: str,
        candidate: Mapping[str, Any],
        provenance: Optional[Mapping[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> Mapping[str, Any]:
        self._log(
            "propose_updates",
            run_id=run_id,
            metadata=provenance,
            assertion_id=assertion_id,
            candidate_fields_count=len(candidate),
            provenance_fields_count=len(provenance) if provenance is not None else None,
        )
        self._ensure_client()
        return {
            "decision": "keep_candidate",
            "reason": "Rosetta stub mantiene la proposta corrente",
            "assertion_id": assertion_id,
            "candidate": dict(candidate),
        }

    def explain(
        self,
        *,
        assertion_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> Mapping[str, Any]:
        self._log(
            "explain",
            run_id=run_id,
            assertion_id=assertion_id,
            trace_id=trace_id,
        )
        self._ensure_client()
        return {
            "assertion_id": assertion_id,
            "trace_id": trace_id,
            "explanation": "Rosetta stub non esegue analisi reale",
            "references": [],
        }


def get_rosetta_client(
    *,
    config: RosettaConfig | None = None,
    settings: Settings | None = None,
    client_factory: Callable[[], Any] | None = None,
    slug: Optional[str] = None,
) -> RosettaClient | None:
    cfg = config or RosettaConfig.load(settings=settings)
    if not cfg.enabled:
        return None
    provider = (cfg.provider or "openai").strip().lower()
    if provider != "openai":
        raise ConfigError(f"rosetta.provider non supportato: {cfg.provider}")
    client = OpenAIRosettaClient(
        slug=slug,
        model=cfg.model,
        client_factory=client_factory,
    )
    client._ensure_client()
    return client
