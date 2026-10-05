"""Survey: question formulation, command caps, read-only artifacts."""

from progettare.survey.artifact import SurveyAnswer, survey_record, write_survey
from progettare.survey.commands import (
    READ_ONLY_COMMANDS,
    READ_ONLY_GIT_SUBCOMMANDS,
    SurveyCommandError,
    validate_session_command,
    validate_session_commands,
)
from progettare.survey.questions import (
    RepoStructure,
    SurveyError,
    SurveyPlan,
    SurveyQuestion,
    formulate,
    observe_repo,
    plan_for,
    structure_from_files,
)
from progettare.survey.stage import (
    SessionOutcome,
    SurveyStageResult,
    answer_one_question,
    fair_share,
    run_survey_stage,
)

__all__ = [
    "READ_ONLY_COMMANDS",
    "READ_ONLY_GIT_SUBCOMMANDS",
    "RepoStructure",
    "SessionOutcome",
    "SurveyAnswer",
    "SurveyCommandError",
    "SurveyError",
    "SurveyPlan",
    "SurveyQuestion",
    "SurveyStageResult",
    "answer_one_question",
    "fair_share",
    "formulate",
    "observe_repo",
    "plan_for",
    "run_survey_stage",
    "structure_from_files",
    "survey_record",
    "validate_session_command",
    "validate_session_commands",
    "write_survey",
]
