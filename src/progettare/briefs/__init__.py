"""The briefs package: reader slices of the blueprint, published as files.

Importing from the module, not the package, keeps one home for the code;
this surface exists so callers read ``progettare.briefs`` the way they
read ``progettare.blueprint``.
"""

from progettare.briefs.briefs import (
    BriefsError,
    DocumenterBrief,
    ImplementerBrief,
    QaBrief,
    run_briefs_stage,
    slice_blueprint,
)

__all__ = [
    "BriefsError",
    "DocumenterBrief",
    "ImplementerBrief",
    "QaBrief",
    "run_briefs_stage",
    "slice_blueprint",
]
