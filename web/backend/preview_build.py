"""Construction-only adapter for the toolkit's familiar build command.

Runs in an isolated toolkit Python process. The upstream parser, plan builder,
syntax checks and atomic output remain intact; Verify Build owns global audits.
"""
from __future__ import annotations

import sys
from pathlib import Path


def run_build(cli, args):
    if args.command != "build":
        raise ValueError("Preview construction accepts only the build command")
    original = cli.geometry_report
    try:
        cli.geometry_report = lambda *_: {
            "diagnostics": [], "complete": False, "deferred_to": "Verify Build",
        }
        report, status = cli.run(args)
    finally:
        cli.geometry_report = original
    report.update(
        construction_checks_passed=report["checks_passed"],
        checks_passed=False, structural_checks_deferred=True,
        build_mode="preview", physical_validity="not_proven",
    )
    return report, status


def main():
    # Do not let backend/ldraw.py shadow the toolkit's installed ldraw package.
    backend = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p).resolve() != backend]
    from ldraw_tools import cli

    args = cli.parser().parse_args()
    try:
        report, status = run_build(cli, args)
    except (OSError, ValueError, cli.PartError, RecursionError, cli.sqlite3.Error,
            cli.subprocess.SubprocessError, cli.jsonschema.ValidationError) as exc:
        report, status = dict(checks_passed=False, build_mode="preview",
                             error=str(exc), error_type=type(exc).__name__), 2
    text = cli.dumps(report) + "\n"
    if getattr(args, "report", None):
        cli.atomic_write(args.report, text)
    print(text, end="")
    return status


if __name__ == "__main__":
    sys.exit(main())
