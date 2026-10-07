"""Project-level `tricc.yaml` schema (see feature/20260915-intervention-start.md)."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tricc_oo.converters.duration import coerce_optional_duration, parse_duration

StartOn = Literal["demand", "follow_up"]
_START_MIGRATION = (
    "kind/applicability were replaced by start: — see feature/20260915-intervention-start.md"
)


class TriccStartWindow(BaseModel):
    """Visibility window around ``due`` (seconds)."""

    model_config = ConfigDict(extra="forbid")

    before: int = 0
    after: int = 0

    @field_validator("before", "after", mode="before")
    @classmethod
    def _parse_side(cls, value: Any) -> int:
        if value is None or value == "":
            return 0
        return parse_duration(value, "window")


class TriccInterventionStart(BaseModel):
    """When a health worker can open this intervention."""

    model_config = ConfigDict(extra="forbid")

    on: StartOn
    intervention: Optional[str] = None
    condition: Optional[str] = None
    due: Optional[int] = None
    window: Optional[TriccStartWindow] = None

    @model_validator(mode="before")
    @classmethod
    def _yaml_on_key(cls, data):
        # PyYAML 1.1 parses the key `on` as boolean True.
        if isinstance(data, dict) and True in data:
            data = dict(data)
            if "on" not in data:
                data["on"] = data.pop(True)
            else:
                data.pop(True, None)
        return data

    @field_validator("intervention", "condition")
    @classmethod
    def _empty_to_none(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("due", mode="before")
    @classmethod
    def _parse_due(cls, value: Any) -> Optional[int]:
        return coerce_optional_duration(value, "due")

    @field_validator("condition")
    @classmethod
    def _parse_cql(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        from tricc_oo.converters.cql_to_operation import transform_cql_to_operation

        parsed = transform_cql_to_operation(value, context="tricc.yaml start.condition")
        if parsed is None:
            raise ValueError(f"start.condition is not valid CQL: {value}")
        return value

    @model_validator(mode="after")
    def _on_constraints(self) -> "TriccInterventionStart":
        if self.on == "demand":
            if self.intervention:
                raise ValueError("start.intervention is only valid when on: follow_up")
            if self.due is not None:
                raise ValueError("start.due is only valid when on: follow_up")
            if "window" in self.model_fields_set and self.window is not None:
                raise ValueError("start.window is only valid when on: follow_up")
        elif self.on == "follow_up":
            if not self.intervention:
                raise ValueError("start.intervention is required when on: follow_up")
            if self.due is None:
                raise ValueError("start.due is required when on: follow_up")
            if self.window is None:
                self.window = TriccStartWindow()
        return self

    def window_or_default(self) -> TriccStartWindow:
        return self.window or TriccStartWindow()


class TriccInterventionConfig(BaseModel):
    """One named algorithm inside a project (e.g. pediatrics vs young infants)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    description: Optional[str] = None
    # Either a list of globs, read with the project's ``input_strategy``, or a mapping
    # ``{InputStrategyName: [globs]}`` so one intervention can mix drawio and yaml
    # activities. See ``activity_groups``.
    activity: Union[List[str], Dict[str, List[str]]] = Field(min_length=1)
    start: List[TriccInterventionStart] = Field(
        default_factory=lambda: [TriccInterventionStart(on="demand")]
    )

    @model_validator(mode="before")
    @classmethod
    def _migrate_and_normalize(cls, data):
        if not isinstance(data, dict):
            return data
        if "segment" in data and "activity" not in data:
            raise ValueError("`segment` was renamed to `activity` in tricc.yaml interventions")
        if "kind" in data or "applicability" in data:
            raise ValueError(_START_MIGRATION)
        start = data.get("start")
        if isinstance(start, dict):
            data = {**data, "start": [start]}
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
    def _non_empty_globs(
        cls, value: Union[List[str], Dict[str, List[str]]]
    ) -> Union[List[str], Dict[str, List[str]]]:
        def clean(globs: List[str], where: str) -> List[str]:
            cleaned = [(g or "").strip() for g in globs or []]
            cleaned = [g for g in cleaned if g]
            if not cleaned:
                raise ValueError(f"{where} must list at least one path glob")
            return cleaned

        if isinstance(value, dict):
            groups: Dict[str, List[str]] = {}
            for strategy, globs in value.items():
                name = (strategy or "").strip()
                if not name:
                    raise ValueError("activity strategy names must be non-empty")
                if name in groups:
                    raise ValueError(f"activity lists strategy {name!r} twice")
                groups[name] = clean(globs, f"activity.{name}")
            return groups
        return clean(value, "activity")

    @field_validator("description")
    @classmethod
    def _empty_description(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    def activity_groups(self, default_strategy: str) -> List[Tuple[str, List[str]]]:
        """``[(input strategy name, globs)]``, in authoring order.

        The list form is a single group read with ``default_strategy`` (the project's
        ``input_strategy`` or the ``-I`` override), exactly as before.
        """
        if isinstance(self.activity, dict):
            return [(name, list(globs)) for name, globs in self.activity.items()]
        return [(default_strategy, list(self.activity))]

    def demand_starts(self) -> List[TriccInterventionStart]:
        return [item for item in self.start if item.on == "demand"]

    def follow_up_starts(self) -> List[TriccInterventionStart]:
        return [item for item in self.start if item.on == "follow_up"]

    def demand_condition(self) -> Optional[str]:
        for item in self.demand_starts():
            if item.condition:
                return item.condition
        return None


class TriccProjectConfig(BaseModel):
    """Root `tricc.yaml` document."""

    model_config = ConfigDict(extra="ignore")

    title: str = "My project"
    input_strategy: str = "DrawioStrategy"
    output_strategies: List[str] = Field(default_factory=list)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    # Project CodeSystems (FHIR JSON): the central concept definitions, loaded into
    # TriccProject.code_systems before any activity. Globs relative to tricc.yaml.
    terminology: List[str] = Field(default_factory=list)
    # CQL libraries; every ``define`` becomes a calculate available to all activities.
    libraries: List[str] = Field(default_factory=list)
    interventions: List[TriccInterventionConfig] = Field(default_factory=list)

    @field_validator("terminology", "libraries")
    @classmethod
    def _clean_globs(cls, value: List[str]) -> List[str]:
        return [(g or "").strip() for g in value if (g or "").strip()]

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
    def _unique_and_follow_up_parents(self) -> "TriccProjectConfig":
        seen = set()
        for item in self.interventions:
            if item.id in seen:
                raise ValueError(f"duplicate intervention id: {item.id}")
            seen.add(item.id)
        for item in self.interventions:
            for start in item.follow_up_starts():
                parent = start.intervention
                if parent == item.id:
                    raise ValueError(f"intervention {item.id!r} cannot follow up on itself")
                if parent not in seen:
                    raise ValueError(
                        f"start.intervention {parent!r} on {item.id!r} is not an intervention id"
                    )
        return self

    def image_max_width(self) -> Optional[int]:
        return coerce_max_dimension(self.parameters.get("image_max_width"), "image_max_width")

    def image_max_height(self) -> Optional[int]:
        return coerce_max_dimension(self.parameters.get("image_max_height"), "image_max_height")

    def languages(self) -> Tuple[Optional[str], List[str]]:
        """``(default, available)`` from ``parameters.languages``.

        Accepts ``{default: en, available: [en, fr]}``, a list (the first entry is the
        default) or a single code. ``(None, [])`` when not configured.
        """
        raw = self.parameters.get("languages")
        if raw is None or raw == "":
            return None, []
        if isinstance(raw, str):
            raw = [raw]
        if isinstance(raw, dict):
            available = [str(c).strip() for c in raw.get("available") or [] if str(c).strip()]
            default = str(raw.get("default") or "").strip() or (available[0] if available else None)
        elif isinstance(raw, list):
            available = [str(c).strip() for c in raw if str(c).strip()]
            default = available[0] if available else None
        else:
            raise ValueError("parameters.languages must be a code, a list or {default, available}")
        if default and default not in available:
            available.insert(0, default)
        return default, available

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
