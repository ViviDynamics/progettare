"""Tests for config loading, validation, and per-stage rail resolution."""

from __future__ import annotations

import pathlib

import pytest

from progettare.config import Config, ConfigError, ModelRail, load_config

SPEC_EXAMPLE = """\
survey:
  max_questions: 12
  per_question_command_budget: 8
budgets:
  survey_stage_tokens: 150000
  blueprint_stage_tokens: 60000
  run_max_tokens: 300000
models:
  default:
    provider: anthropic
    model: claude-best
  overrides:
    survey:
      provider: openai
      base_url: https://litellm.internal/v1
      model: cheap-survey-model
    blueprint:
      model: even-better
size:
  single_turn_max_milestones: 2
  documenter_min_topics: 1
"""


def write_config(tmp_path: pathlib.Path, text: str) -> pathlib.Path:
    path = tmp_path / "progettare.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_spec_example_loads_and_resolves_rails(tmp_path: pathlib.Path) -> None:
    config = load_config(write_config(tmp_path, SPEC_EXAMPLE))
    assert config.survey_max_questions == 12
    assert config.survey_per_question_command_budget == 8
    assert config.budget_survey_stage_tokens == 150000
    assert config.budget_blueprint_stage_tokens == 60000
    assert config.budget_run_max_tokens == 300000
    assert config.size_single_turn_max_milestones == 2
    assert config.size_documenter_min_topics == 1
    assert config.survey_rail == ModelRail(
        provider="openai",
        model="cheap-survey-model",
        base_url="https://litellm.internal/v1",
    )
    assert config.blueprint_rail == ModelRail(
        provider="anthropic", model="even-better", base_url=None
    )


def test_rail_accessor_maps_stages(tmp_path: pathlib.Path) -> None:
    config = load_config(write_config(tmp_path, SPEC_EXAMPLE))
    assert config.rail("survey") is config.survey_rail
    assert config.rail("blueprint") is config.blueprint_rail
    with pytest.raises(ValueError, match="unknown stage 'nonsense'"):
        config.rail("nonsense")


def test_without_overrides_both_stages_use_the_default_rail(
    tmp_path: pathlib.Path,
) -> None:
    text = SPEC_EXAMPLE.replace(
        """  overrides:
    survey:
      provider: openai
      base_url: https://litellm.internal/v1
      model: cheap-survey-model
    blueprint:
      model: even-better
""",
        "",
    )
    config = load_config(write_config(tmp_path, text))
    expected = ModelRail(provider="anthropic", model="claude-best", base_url=None)
    assert config.survey_rail == expected
    assert config.blueprint_rail == expected


def test_partial_override_inherits_unspecified_fields(
    tmp_path: pathlib.Path,
) -> None:
    text = SPEC_EXAMPLE.replace(
        "    blueprint:\n      model: even-better\n",
        "    blueprint:\n      base_url: https://proxy.internal/v1\n",
    )
    config = load_config(write_config(tmp_path, text))
    assert config.blueprint_rail == ModelRail(
        provider="anthropic",
        model="claude-best",
        base_url="https://proxy.internal/v1",
    )


def test_unknown_top_level_key_is_named(tmp_path: pathlib.Path) -> None:
    text = "mystery:\n  value: 1\n" + SPEC_EXAMPLE
    with pytest.raises(ConfigError, match="unknown key\\(s\\): mystery"):
        load_config(write_config(tmp_path, text))


def test_unknown_nested_key_is_named_with_its_path(
    tmp_path: pathlib.Path,
) -> None:
    text = SPEC_EXAMPLE.replace(
        "  max_questions: 12\n", "  max_questions: 12\n  extra: 1\n"
    )
    with pytest.raises(ConfigError, match="unknown key\\(s\\): survey.extra"):
        load_config(write_config(tmp_path, text))


@pytest.mark.parametrize(
    ("drop_line", "key"),
    [
        ("max_questions: 12", "survey.max_questions"),
        ("per_question_command_budget: 8", "survey.per_question_command_budget"),
        ("survey_stage_tokens: 150000", "budgets.survey_stage_tokens"),
        ("blueprint_stage_tokens: 60000", "budgets.blueprint_stage_tokens"),
        ("run_max_tokens: 300000", "budgets.run_max_tokens"),
        ("single_turn_max_milestones: 2", "size.single_turn_max_milestones"),
        ("documenter_min_topics: 1", "size.documenter_min_topics"),
        ("model: claude-best", "models.default.model"),
        ("provider: anthropic", "models.default.provider"),
    ],
)
def test_missing_required_value_names_the_key(
    tmp_path: pathlib.Path, drop_line: str, key: str
) -> None:
    text = SPEC_EXAMPLE.replace(drop_line, "", 1)
    assert drop_line in SPEC_EXAMPLE
    with pytest.raises(ConfigError, match=f"{key} is required"):
        load_config(write_config(tmp_path, text))


def swap_line(bad_line: str) -> str:
    leaf = bad_line.split(":")[0] + ":"
    lines = SPEC_EXAMPLE.splitlines()
    index = next(i for i, line in enumerate(lines) if line.strip().startswith(leaf))
    indent = lines[index][: len(lines[index]) - len(lines[index].lstrip())]
    lines[index] = indent + bad_line
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize(
    ("bad_line", "key"),
    [
        ("max_questions: twelve", "survey.max_questions"),
        ("max_questions: true", "survey.max_questions"),
        ("max_questions: 1.5", "survey.max_questions"),
        ("per_question_command_budget: 0", "survey.per_question_command_budget"),
        ("survey_stage_tokens: -1", "budgets.survey_stage_tokens"),
        ("blueprint_stage_tokens: 0", "budgets.blueprint_stage_tokens"),
        ("run_max_tokens: 0", "budgets.run_max_tokens"),
        ("single_turn_max_milestones: 0", "size.single_turn_max_milestones"),
        ("documenter_min_topics: -2", "size.documenter_min_topics"),
        ("provider: 7", "models.default.provider"),
        ("model: null", "models.default.model"),
        ("base_url: 3", "models.overrides.survey.base_url"),
    ],
)
def test_type_errors_and_bounds_name_the_key(
    tmp_path: pathlib.Path, bad_line: str, key: str
) -> None:
    text = swap_line(bad_line)
    assert text != SPEC_EXAMPLE
    with pytest.raises(ConfigError, match=key):
        load_config(write_config(tmp_path, text))


def test_section_that_is_not_a_mapping_is_named(tmp_path: pathlib.Path) -> None:
    text = SPEC_EXAMPLE.replace(
        "survey:\n  max_questions: 12\n  per_question_command_budget: 8\n",
        "survey: 4\n",
        1,
    )
    with pytest.raises(ConfigError, match="survey must be a mapping"):
        load_config(write_config(tmp_path, text))


def test_models_default_that_is_not_a_mapping_is_named(
    tmp_path: pathlib.Path,
) -> None:
    text = SPEC_EXAMPLE.replace(
        "  default:\n    provider: anthropic\n    model: claude-best\n",
        "  default: yes\n",
        1,
    )
    with pytest.raises(ConfigError, match="models.default must be a mapping"):
        load_config(write_config(tmp_path, text))


def test_unknown_override_stage_is_named(tmp_path: pathlib.Path) -> None:
    text = SPEC_EXAMPLE.replace(
        "  overrides:\n    survey:\n",
        "  overrides:\n    mystery:\n      model: m\n    survey:\n",
    )
    with pytest.raises(ConfigError, match="models.overrides.mystery is not a stage"):
        load_config(write_config(tmp_path, text))


def test_unknown_override_key_is_named(tmp_path: pathlib.Path) -> None:
    text = SPEC_EXAMPLE.replace(
        "      model: even-better\n", "      model: even-better\n      extra: 1\n"
    )
    with pytest.raises(
        ConfigError, match="unknown key\\(s\\): models.overrides.blueprint.extra"
    ):
        load_config(write_config(tmp_path, text))


def test_override_that_is_not_a_mapping_is_named(tmp_path: pathlib.Path) -> None:
    text = SPEC_EXAMPLE.replace(
        """    survey:
      provider: openai
      base_url: https://litellm.internal/v1
      model: cheap-survey-model
""",
        "    survey: 7\n",
        1,
    )
    with pytest.raises(ConfigError, match="models.overrides.survey must be a mapping"):
        load_config(write_config(tmp_path, text))


def test_overrides_that_is_not_a_mapping_is_named(tmp_path: pathlib.Path) -> None:
    text = SPEC_EXAMPLE.replace(
        """  overrides:
    survey:
      provider: openai
      base_url: https://litellm.internal/v1
      model: cheap-survey-model
    blueprint:
      model: even-better
""",
        "  overrides: nope\n",
        1,
    )
    with pytest.raises(ConfigError, match="models.overrides must be a mapping"):
        load_config(write_config(tmp_path, text))


def test_missing_file_names_the_path(tmp_path: pathlib.Path) -> None:
    with pytest.raises(ConfigError, match="no config file at"):
        load_config(tmp_path / "absent.yaml")


def test_invalid_yaml_names_the_file(tmp_path: pathlib.Path) -> None:
    path = write_config(tmp_path, "survey: [unclosed\n  bad: , here")
    with pytest.raises(ConfigError, match="is not valid YAML"):
        load_config(path)


def test_empty_file_reports_missing_top_level_mapping(
    tmp_path: pathlib.Path,
) -> None:
    path = write_config(tmp_path, "")
    with pytest.raises(ConfigError, match="expected a mapping at the top level"):
        load_config(path)


def test_document_that_is_a_list_is_refused(tmp_path: pathlib.Path) -> None:
    path = write_config(tmp_path, "- just\n- a\n- list\n")
    with pytest.raises(ConfigError, match="expected a mapping at the top level"):
        load_config(path)


def test_models_section_missing_names_the_key(tmp_path: pathlib.Path) -> None:
    text = SPEC_EXAMPLE.replace(
        """models:
  default:
    provider: anthropic
    model: claude-best
  overrides:
    survey:
      provider: openai
      base_url: https://litellm.internal/v1
      model: cheap-survey-model
    blueprint:
      model: even-better
""",
        "",
        1,
    )
    with pytest.raises(ConfigError, match="models is required"):
        load_config(write_config(tmp_path, text))


def test_config_and_model_rail_are_importable_surface() -> None:
    assert Config is not None
    assert ModelRail is not None
