from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from loguru import logger

from nure_dl.service import download_ungraded
from nure_dl.settings import load_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download ungraded Moodle assignment submissions for all lab groups "
            "on one or more courses into a local folder (gitignored)."
        )
    )
    parser.add_argument(
        "--course-id",
        type=int,
        action="append",
        default=None,
        help="Course id (repeatable). Overrides MOODLE_COURSE_IDS from .env",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Override output directory (default: downloads/)",
    )
    parser.add_argument(
        "--group",
        default=None,
        help="Only labs whose group name contains this substring (e.g. КІУКІ-23-1)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List destination paths without downloading",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    updates: dict = {}
    if args.course_id:
        updates["course_ids"] = tuple(args.course_id)
    if args.output is not None:
        updates["output_dir"] = Path(args.output)
    if updates:
        settings = replace(settings, **updates)

    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<level>{message}</level>")

    count = download_ungraded(
        settings,
        dry_run=args.dry_run,
        group_filter=args.group,
    )
    action = "Would download" if args.dry_run else "Downloaded"
    logger.info(
        "{} {} file(s) from courses {} → {}",
        action,
        count,
        ",".join(str(c) for c in settings.course_ids),
        settings.output_dir.resolve(),
    )


if __name__ == "__main__":
    main()
