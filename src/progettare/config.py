"""Config loading and validation: the run's budget, rails, and caps.

Everything the pipeline is allowed to spend or call comes from
``progettare.yaml``. The file is small on purpose, and every failure is a
startup failure that names the offending key: a config that is half-accepted
at runtime is a config that spends money badly.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Any

import yaml


class ConfigError(ValueError):
    """A progettare.yaml progettare refuses to run, naming the key."""


_STAGES = ("survey", "blueprint")


@dataclass(frozen=True)
class ModelRail:
    """The provider, model, and optional endpoint one stage calls through."""

    provider: str
    model: str
    base_url: str | None = None


@dataclass(frozen=True)
class Config:
    """A validated progettare.yaml, with model rails resolved per stage."""

    survey_max_questions: int
    survey_per_question_command_budget: int
    budget_survey_stage_tokens: int
    budget_blueprint_stage_tokens: int
    budget_run_max_tokens: int
    size_single_turn_max_milestones: int
    size_documenter_min_topics: int
    survey_rail: ModelRail
    blueprint_rail: ModelRail

    def rail(self, stage: str) -> ModelRail:
        """The resolved rail for a named pipeline stage."""
        if stage == "survey":
            return self.survey_rail
        if stage == "blueprint":
            return self.blueprint_rail
        raise ValueError(
            f"unknown stage {stage!r}; expected one of {', '.join(_STAGES)}"
        )


def _require_dict(data: Any, key: str) -> dict[str, Any]:
    section = data.get(key)
    if section is None:
        raise ConfigError(f"{key} is required")
    if not isinstance(section, dict):
        raise ConfigError(f"{key} must be a mapping, got {_type_name(section)}")
    return section


def _require_keys(section: dict[str, Any], known: tuple[str, ...], path: str) -> None:
    unknown = sorted(set(section) - set(known))
    if unknown:
        names = ", ".join(f"{path}.{key}" if path else str(key) for key in unknown)
        raise ConfigError(f"unknown key(s): {names}")


def _type_name(value: Any) -> str:
    if value is None:
        return "a missing value"
    return type(value).__name__


def _leaf(path: str) -> str:
    return path.rsplit(".", 1)[-1]


def _require_int(section: dict[str, Any], key: str, minimum: int) -> int:
    if _leaf(key) not in section:
        raise ConfigError(f"{key} is required")
    value = section[_leaf(key)]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key} must be an integer, got {type(value).__name__}")
    if value < minimum:
        raise ConfigError(f"{key} must be at least {minimum}, got {value}")
    return value


def _require_str(section: dict[str, Any], key: str) -> str:
    if _leaf(key) not in section:
        raise ConfigError(f"{key} is required")
    value = section[_leaf(key)]
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(
            f"{key} must be a non-empty string, got {type(value).__name__}"
        )
    return value


def _optional_str(section: dict[str, Any], key: str) -> str | None:
    value = section.get(_leaf(key))
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(
            f"{key} must be a non-empty string, got {type(value).__name__}"
        )
    return value


def _parse_rail(section: dict[str, Any], path: str) -> ModelRail:
    _require_keys(section, ("provider", "model", "base_url"), path)
    return ModelRail(
        provider=_require_str(section, f"{path}.provider"),
        model=_require_str(section, f"{path}.model"),
        base_url=_optional_str(section, f"{path}.base_url"),
    )


def _resolve_rail(default: ModelRail, override: dict[str, Any], path: str) -> ModelRail:
    _require_keys(override, ("provider", "model", "base_url"), path)
    provider = default.provider
    model = default.model
    base_url = default.base_url
    if "provider" in override:
        provider = _require_str(override, f"{path}.provider")
    if "model" in override:
        model = _require_str(override, f"{path}.model")
    if "base_url" in override:
        base_url = _optional_str(override, f"{path}.base_url")
    return ModelRail(provider=provider, model=model, base_url=base_url)


def config_from_mapping(data: Any) -> Config:
    """Validate a parsed config document, naming every offending key."""
    if not isinstance(data, dict):
        raise ConfigError(
            f"expected a mapping at the top level, got {_type_name(data)}"
        )
    _require_keys(data, ("survey", "budgets", "models", "size"), "")

    survey = _require_dict(data, "survey")
    _require_keys(survey, ("max_questions", "per_question_command_budget"), "survey")
    budgets = _require_dict(data, "budgets")
    _require_keys(
        budgets,
        ("survey_stage_tokens", "blueprint_stage_tokens", "run_max_tokens"),
        "budgets",
    )
    size = _require_dict(data, "size")
    _require_keys(size, ("single_turn_max_milestones", "documenter_min_topics"), "size")

    models = _require_dict(data, "models")
    _require_keys(models, ("default", "overrides"), "models")
    default_section = models.get("default")
    if default_section is None:
        raise ConfigError("models.default is required")
    if not isinstance(default_section, dict):
        raise ConfigError(
            f"models.default must be a mapping, got {_type_name(default_section)}"
        )
    default_rail = _parse_rail(default_section, "models.default")

    overrides = models.get("overrides", {})
    if not isinstance(overrides, dict):
        raise ConfigError(
            f"models.overrides must be a mapping, got {_type_name(overrides)}"
        )
    rails: dict[str, ModelRail] = {}
    for stage, override in overrides.items():
        if stage not in _STAGES:
            raise ConfigError(
                f"models.overrides.{stage} is not a stage; "
                f"expected one of {', '.join(_STAGES)}"
            )
        if not isinstance(override, dict):
            raise ConfigError(
                f"models.overrides.{stage} must be a mapping, "
                f"got {_type_name(override)}"
            )
        rails[stage] = _resolve_rail(
            default_rail, override, f"models.overrides.{stage}"
        )

    return Config(
        survey_max_questions=_require_int(survey, "survey.max_questions", 1),
        survey_per_question_command_budget=_require_int(
            survey, "survey.per_question_command_budget", 1
        ),
        budget_survey_stage_tokens=_require_int(
            budgets, "budgets.survey_stage_tokens", 1
        ),
        budget_blueprint_stage_tokens=_require_int(
            budgets, "budgets.blueprint_stage_tokens", 1
        ),
        budget_run_max_tokens=_require_int(budgets, "budgets.run_max_tokens", 1),
        size_single_turn_max_milestones=_require_int(
            size, "size.single_turn_max_milestones", 1
        ),
        size_documenter_min_topics=_require_int(size, "size.documenter_min_topics", 0),
        survey_rail=rails.get("survey", default_rail),
        blueprint_rail=rails.get("blueprint", default_rail),
    )


def load_config(path: pathlib.Path) -> Config:
    """Read, parse, and validate ``progettare.yaml`` at ``path``."""
    if not path.is_file():
        raise ConfigError(f"no config file at {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ConfigError(f"{path} is not valid YAML: {error}") from error
    return config_from_mapping(data)
