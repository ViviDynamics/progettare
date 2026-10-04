"""Command line interface."""

import argparse
import os
import sys

from progettare.engine.intake import IntakeAborted, IntakeError, run_intake
from progettare.engine.issue_fetch import GhError, Runner, gh_runner
from progettare.engine.issue_ref import IssueRefError, parse_issue_ref


def main(argv: list[str] | None = None, run: Runner = gh_runner) -> int:
    parser = argparse.ArgumentParser(prog="progettare")
    commands = parser.add_subparsers(dest="command", required=True)
    intake = commands.add_parser("intake")
    intake.add_argument("issue_ref")
    intake.add_argument("--repo", required=True)
    intake.add_argument("--run-dir", default="run")
    args = parser.parse_args(argv)
    try:
        ref = parse_issue_ref(args.issue_ref)
    except IssueRefError as error:
        print(f"progettare: {error}", file=sys.stderr)
        return 1
    try:
        run_intake(ref, args.repo, args.run_dir, run)
    except IntakeAborted as error:
        print(f"progettare: aborted: {error}", file=sys.stderr)
        return 1
    except (GhError, IntakeError) as error:
        print(f"progettare: {error}", file=sys.stderr)
        return 1
    artifact = os.path.join(args.run_dir, "intake.json")
    with open(artifact, encoding="utf-8") as handle:
        sys.stdout.write(handle.read())
    return 0


if __name__ == "__main__":
    main()
