"""Project-level `tricc.yaml` schema (see feature/20260907-project-config.md)."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


InterventionKind = Literal["on_demand", "task", "both"]


class TriccInterventionConfig(BaseModel):
    """One named algorithm inside a project (e.g. pediatrics vs young infants)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    kind: InterventionKind = "on_demand"
    applicability: Optional[str] = None
    description: Optional[str] = None
    activity: List[str] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _reject_legacy_segment_key(cls, data):
        if isinstance(data, dict) and "segment" in data and "activity" not in data:
            raise ValueError("`segment` was renamed to `activity` in tricc.yaml interventions")
        return data

    @field_validator("id", "title")
    @classmethod
    def _non_empty_str(cls, value: str) -> str:
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("must be a non-empty string")
        return stripped

    @field_validator("activity")
    @classmethod
    def _non_empty_globs(cls, value: List[str]) -> List[str]:
        cleaned = [(g or "").strip() for g in value]
        cleaned = [g for g in cleaned if g]
        if not cleaned:
            raise ValueError("activity must list at least one path glob")
        return cleaned

    @field_validator("applicability", "description")
    @classmethod
    def _empty_to_none(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class TriccProjectConfig(BaseModel):
    """Root `tricc.yaml` document."""

    model_config = ConfigDict(extra="ignore")

    title: str = "My project"
    input_strategy: str = "DrawioStrategy"
    output_strategies: List[str] = Field(default_factory=list)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    interventions: List[TriccInterventionConfig] = Field(default_factory=list)

    @field_validator("title", "input_strategy")
    @classmethod
    def _non_empty_str(cls, value: str) -> str:
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("must be a non-empty string")
        return stripped

    @field_validator("output_strategies")
    @classmethod
    def _clean_strategy_names(cls, value: List[str]) -> List[str]:
        return [(s or "").strip() for s in value if (s or "").strip()]

    @model_validator(mode="after")
    def _unique_intervention_ids(self) -> "TriccProjectConfig":
        seen = set()
        for item in self.interventions:
            if item.id in seen:
                raise ValueError(f"duplicate intervention id: {item.id}")
            seen.add(item.id)
        return self

    def image_max_width(self) -> Optional[int]:
        return coerce_max_dimension(self.parameters.get("image_max_width"), "image_max_width")

    def image_max_height(self) -> Optional[int]:
        return coerce_max_dimension(self.parameters.get("image_max_height"), "image_max_height")

    def tricc_version(self) -> Optional[str]:
        raw = self.parameters.get("tricc_version")
        if raw is None:
            return None
        text = str(raw).strip()
        return text or None


def coerce_max_dimension(value: Any, field_name: str) -> Optional[int]:
    """Parse a pixel cap. ``None`` / omitted / ``0`` mean unlimited. Negatives error."""
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer pixel cap") from exc
    if number < 0:
        raise ValueError(f"{field_name} must be >= 0 (0 = no cap)")
    if number == 0:
        return None
    return number
