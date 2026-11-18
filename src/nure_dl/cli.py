from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

from loguru import logger

from nure_dl.comments import post_submission_comment
from nure_dl.dump import dump_report
from nure_dl.grade import prepare_grade, print_prep, save_grade_result
from nure_dl.index import get_submission, load_index, reindex_from_disk
from nure_dl.mark import submit_assignment_grade
from nure_dl.service import download_ungraded
from nure_dl.settings import load_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ХНУРЕ DL helpers: download, index, dump, grade submissions."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    download = sub.add_parser(
        "download",
        help="Download ungraded submissions and index them under downloads/",
    )
    download.add_argument(
        "--course-id",
        type=int,
        action="append",
        default=None,
        help="Course id (repeatable). Overrides MOODLE_COURSE_IDS from .env",
    )
    download.add_argument(
        "--output",
        default=None,
        help="Override output directory (default: downloads/)",
    )
    download.add_argument(
        "--group",
        default=None,
        help="Only labs whose group name contains this substring",
    )
    download.add_argument(
        "--dry-run",
        action="store_true",
        help="List destination paths without downloading",
    )

    dump = sub.add_parser(
        "dump",
        help="Write report text.txt + images/ for reading (no grading)",
    )
    dump.add_argument("path", type=Path, help="PDF or DOCX report")
    dump.add_argument(
        "-o",
        "--out",
        type=Path,
        default=Path("/tmp/nure-report-dump"),
        help="Output directory (default: /tmp/nure-report-dump)",
    )

    grade = sub.add_parser(
        "grade",
        help="Prepare any cached submission for grading by id (lab-agnostic)",
    )
    grade.add_argument("submission_id", help="Id from submissions.json")
    grade.add_argument(
        "--output",
        default=None,
        help="Downloads root containing submissions.json",
    )
    grade.add_argument(
        "--save",
        type=Path,
        default=None,
        help="Optional JSON file with {summary, tasks:[...]} to store under grades.json",
    )
    grade.add_argument(
        "--score",
        "-s",
        default=None,
        help="If set, submit this numeric grade to Moodle (assignment gradebook)",
    )
    grade.add_argument(
        "--notify",
        action="store_true",
        help="With --score, also send the Moodle grade notification to the student",
    )
    grade.add_argument(
        "--comment",
        "-c",
        default=None,
        help="If set, post this text to the Moodle submission comments section",
    )
    grade.add_argument(
        "--comment-file",
        type=Path,
        default=None,
        help="Read Moodle submission comment text from a file (UTF-8)",
    )

    subs = sub.add_parser(
        "submissions",
        help="List or resolve cached submission ids (from download index)",
    )
    subs.add_argument(
        "submission_id",
        nargs="?",
        default=None,
        help="If set, print that record (path + metadata)",
    )
    subs.add_argument(
        "--output",
        default=None,
        help="Downloads root containing submissions.json",
    )
    subs.add_argument(
        "--json",
        action="store_true",
        help="Machine-readable JSON",
    )
    subs.add_argument(
        "--reindex",
        action="store_true",
        help="Scan downloads/ and register files missing from the index",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<level>{message}</level>")

    if args.command == "download":
        _cmd_download(args)
    elif args.command == "dump":
        dump_report(args.path, args.out)
    elif args.command == "grade":
        _cmd_grade(args)
    elif args.command == "submissions":
        raise SystemExit(_cmd_submissions(args))
    else:
        raise SystemExit(f"unknown command: {args.command}")


def _cmd_download(args: argparse.Namespace) -> None:
    settings = load_settings()
    updates: dict = {}
    if args.course_id:
        updates["course_ids"] = tuple(args.course_id)
    if args.output is not None:
        updates["output_dir"] = Path(args.output)
    if updates:
        settings = replace(settings, **updates)

    count = download_ungraded(
        settings,
        dry_run=args.dry_run,
        group_filter=args.group,
    )
    action = "Would download" if args.dry_run else "Downloaded"
    logger.info(
        "{} {} file(s) from courses {} → {} (index: {}/submissions.json)",
        action,
        count,
        ",".join(str(c) for c in settings.course_ids),
        settings.output_dir.resolve(),
        settings.output_dir.resolve(),
    )


def _cmd_grade(args: argparse.Namespace) -> None:
    settings = load_settings()
    root = Path(args.output) if args.output else settings.output_dir
    prep = prepare_grade(root, args.submission_id)
    print_prep(prep)
    if args.save is not None:
        payload = json.loads(Path(args.save).read_text(encoding="utf-8"))
        path = save_grade_result(
            root,
            args.submission_id,
            tasks=list(payload.get("tasks", [])),
            summary=payload.get("summary"),
            score=payload.get("score", args.score),
        )
        logger.info("Saved grade → {}", path)
    if args.score is not None:
        stored = submit_assignment_grade(
            settings,
            prep.submission,
            args.score,
            output_dir=root,
            notify_student=args.notify,
        )
        print(f"moodle_grade: {stored}")
    comment = _grade_comment_text(args)
    if comment is not None:
        posted = post_submission_comment(
            settings,
            prep.submission,
            comment,
            output_dir=root,
        )
        print(f"moodle_comment_id: {posted['id']}")


def _grade_comment_text(args: argparse.Namespace) -> str | None:
    if args.comment is not None and args.comment_file is not None:
        raise SystemExit("Use only one of --comment / --comment-file")
    if args.comment_file is not None:
        return args.comment_file.read_text(encoding="utf-8")
    if args.comment is not None:
        return args.comment
    return None


def _cmd_submissions(args: argparse.Namespace) -> int:
    settings = load_settings()
    root = Path(args.output) if args.output else settings.output_dir
    if args.reindex:
        records = reindex_from_disk(root)
        logger.info("Indexed {} submission(s) → {}", len(records), root / "submissions.json")
        if args.submission_id is None and not args.json:
            return 0
    if args.submission_id:
        rec = get_submission(root, args.submission_id)
        if rec is None:
            logger.error("Unknown submission id: {}", args.submission_id)
            return 1
        if args.json:
            print(json.dumps(asdict(rec), ensure_ascii=False, indent=2))
        else:
            print(f"id:       {rec.id}")
            print(f"path:     {rec.path}")
            print(f"student:  {rec.student_name} <{rec.student_email}>")
            print(f"lab:      {rec.lab_title} ({rec.group})")
            print(f"assign:   {rec.assign_id}  course={rec.course_id}")
            print(f"moodle:   user={rec.moodle_user_id} file={rec.moodle_file_id}")
        return 0

    records = load_index(root)
    if args.json:
        print(
            json.dumps(
                [asdict(records[k]) for k in sorted(records)],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if not records:
            logger.info("No submissions indexed in {}", root / "submissions.json")
            return 0
        for sid in sorted(records):
            rec = records[sid]
            print(f"{rec.id}\t{rec.student_name}\t{rec.group}\t{rec.lab_title}")
        logger.info("{} submission(s) in {}", len(records), root / "submissions.json")
    return 0


if __name__ == "__main__":
    main()
