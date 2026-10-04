"""progettare: a technical-planning agent harness.

Given an issue and a repository, progettare runs a bounded, read-only
pipeline: intake, survey, blueprint, size, report. Every model call goes
through nare; code decides what is asked, validates what is produced, and
derives every downstream artifact.
"""

from progettare.contract import PROGETTARE_VERSION

__version__ = PROGETTARE_VERSION

__all__ = ["__version__"]
