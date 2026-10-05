"""Blueprint: the run's one structured plan, validated and versioned."""

from progettare.blueprint.artifact import (
    BLUEPRINT_RECORD_VERSION,
    BlueprintRecord,
    BlueprintRecordError,
    Milestone,
    blueprint_record,
    write_blueprint,
)
from progettare.blueprint.size import (
    MILESTONE_LOOP,
    SINGLE_TURN,
    SIZE_RECORD_VERSION,
    SizeStageError,
    classify_size,
    write_size,
)
from progettare.blueprint.slices import (
    BRIEFS_RECORD_VERSION,
    READERS,
    SliceStageError,
    brief_files,
    slice_briefs,
    write_briefs,
)
from progettare.blueprint.stage import (
    BLUEPRINT_SCHEMA,
    BLUEPRINT_SYSTEM_PROMPT,
    BlueprintStageError,
    BlueprintStageResult,
    run_blueprint_stage,
    validate_blueprint,
)

__all__ = [
    "BLUEPRINT_RECORD_VERSION",
    "BLUEPRINT_SCHEMA",
    "BLUEPRINT_SYSTEM_PROMPT",
    "BlueprintRecord",
    "BlueprintRecordError",
    "BlueprintStageError",
    "BlueprintStageResult",
    "BRIEFS_RECORD_VERSION",
    "MILESTONE_LOOP",
    "Milestone",
    "READERS",
    "SINGLE_TURN",
    "SIZE_RECORD_VERSION",
    "SizeStageError",
    "SliceStageError",
    "blueprint_record",
    "brief_files",
    "classify_size",
    "run_blueprint_stage",
    "slice_briefs",
    "validate_blueprint",
    "write_briefs",
    "write_blueprint",
    "write_size",
]
