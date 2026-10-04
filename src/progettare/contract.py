"""The versioned shapes callers build on.

progettare's contract with its callers has two layers: the run artifacts
(intake.json, survey.json, blueprint.json, size.json, briefs/) and, from M2,
the CLI's JSON result on stdout. A change a caller could mis-read bumps the
version rather than arriving silently. One number at a time; additive
changes keep the number.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

# The release that produced a run. Read from the installed distribution when
# there is one, so a wheel's metadata and what progettare reports can never
# disagree; the fallback is for a source checkout, which has no distribution
# to read.
try:  # pragma: no cover - exercised by whichever branch the environment takes
    PROGETTARE_VERSION = version("progettare")
except PackageNotFoundError:  # pragma: no cover
    PROGETTARE_VERSION = "0.0.0+source"

# The artifact schema version stamped into every run artifact. It is the
# number a consumer of intake.json checks before it reads the rest.
ARTIFACT_VERSION = 1
