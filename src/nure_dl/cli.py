from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

from loguru import logger

from nure_dl.clean import clean_graded_submissions, clean_result_as_dict
from nure_dl.comments import post_submission_comment
from nure_dl.dump import dump_report
from nure_dl.grade import prepare_grade, print_prep, save_grade_result
from nure_dl.grade_cap import (
    apply_grade_cap,
    compute_grade_cap,
    grade_cap_as_dict,
    grade_cap_for_submission,
)
from nure_dl.grade_status import check_grade_status, grade_status_as_dict
from nure_dl.index import get_submission, load_index, reindex_from_disk
from nure_dl.mark import submit_assignment_grade
from nure_dl.schedule import (
    ensure_lab_held_date,
    held_path,
    lab_number_from_title,
    load_parsed_schedule,
    write_parsed_schedule,
)
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
    download.add_argument(
        "--force",
        action="store_true",
        help="Re-download even when the local file already exists",
    )

    clean = sub.add_parser(
        "clean-graded",
        help="Delete local files for submissions already graded on Moodle",
    )
    clean.add_argument(
        "--output",
        default=None,
        help="Downloads root containing submissions.json",
    )
    clean.add_argument(
        "--group",
        default=None,
        help="Only submissions whose group name contains this substring",
    )
    clean.add_argument(
        "--lab",
        type=int,
        default=None,
        help="Only this lab number (from lab title)",
    )
    clean.add_argument(
        "--dry-run",
        action="store_true",
        help="List graded locals without deleting",
    )
    clean.add_argument("--json", action="store_true", help="Machine-readable JSON")

    refresh = sub.add_parser(
        "refresh",
        help="Re-download all currently ungraded Moodle submissions (force)",
    )
    refresh.add_argument(
        "--course-id",
        type=int,
        action="append",
        default=None,
        help="Course id (repeatable). Overrides MOODLE_COURSE_IDS from .env",
    )
    refresh.add_argument(
        "--output",
        default=None,
        help="Override output directory (default: downloads/)",
    )
    refresh.add_argument(
        "--group",
        default=None,
        help="Only labs whose group name contains this substring",
    )
    refresh.add_argument(
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

    sched = sub.add_parser(
        "schedule-parse",
        help="Parse local/schedule/*.html into local/schedule/parsed.json",
    )
    sched.add_argument(
        "--schedule-dir",
        type=Path,
        default=None,
        help="Schedule directory (default: local/schedule)",
    )
    sched.add_argument(
        "--html",
        type=Path,
        default=None,
        help="Specific HTML file (default: first *.html in schedule dir)",
    )

    held = sub.add_parser(
        "held-date",
        help="Resolve/cache when a lab was held (uses parsed schedule; before evaluate)",
    )
    held.add_argument(
        "submission_id",
        nargs="?",
        default=None,
        help="Optional submission id — uses its group + lab title",
    )
    held.add_argument("--subject", default="tpks", help="Guidelines subject slug")
    held.add_argument("--lab", type=int, default=None, help="Lab number (1, 2, …)")
    held.add_argument("--group", default=None, help="Group name (e.g. КІУКІ-24-3)")
    held.add_argument(
        "--output",
        default=None,
        help="Downloads root when resolving via submission_id",
    )
    held.add_argument("--json", action="store_true", help="Machine-readable JSON")

    status = sub.add_parser(
        "grade-status",
        help="Check whether a submission is already graded on Moodle (skip if yes)",
    )
    status.add_argument("submission_id", help="Id from submissions.json")
    status.add_argument(
        "--output",
        default=None,
        help="Downloads root containing submissions.json",
    )
    status.add_argument("--json", action="store_true", help="Machine-readable JSON")

    cap = sub.add_parser(
        "grade-cap",
        help="Max grade from lateness (held-on vs submission date): 100 / 90 / 80",
    )
    cap.add_argument(
        "submission_id",
        nargs="?",
        default=None,
        help="Submission id — uses held-date cache + Moodle file time",
    )
    cap.add_argument(
        "--held", default=None, help="Held-on date YYYY-MM-DD / dd.mm.yyyy"
    )
    cap.add_argument(
        "--submitted",
        default=None,
        help="Submission date YYYY-MM-DD / dd.mm.yyyy (with --held)",
    )
    cap.add_argument("--subject", default="tpks", help="Guidelines subject slug")
    cap.add_argument(
        "--lab", type=int, default=None, help="Lab number when using submission_id"
    )
    cap.add_argument(
        "--score",
        type=float,
        default=None,
        help="Optional task score to clamp under the cap",
    )
    cap.add_argument("--output", default=None, help="Downloads root for submission_id")
    cap.add_argument("--json", action="store_true", help="Machine-readable JSON")

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
    elif args.command == "clean-graded":
        raise SystemExit(_cmd_clean_graded(args))
    elif args.command == "refresh":
        _cmd_refresh(args)
    elif args.command == "dump":
        dump_report(args.path, args.out)
    elif args.command == "grade":
        _cmd_grade(args)
    elif args.command == "schedule-parse":
        raise SystemExit(_cmd_schedule_parse(args))
    elif args.command == "held-date":
        raise SystemExit(_cmd_held_date(args))
    elif args.command == "grade-status":
        raise SystemExit(_cmd_grade_status(args))
    elif args.command == "grade-cap":
        raise SystemExit(_cmd_grade_cap(args))
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
        force=args.force,
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


def _cmd_clean_graded(args: argparse.Namespace) -> int:
    settings = load_settings()
    root = Path(args.output) if args.output else settings.output_dir
    result = clean_graded_submissions(
        settings,
        output_dir=root,
        group_filter=args.group,
        lab_filter=args.lab,
        dry_run=args.dry_run,
    )
    if args.json:
        print(json.dumps(clean_result_as_dict(result), ensure_ascii=False, indent=2))
    else:
        print(f"checked:  {result.checked}")
        print(f"graded:   {result.graded}")
        print(f"removed:  {result.removed}{' (dry-run)' if result.dry_run else ''}")
        print(f"kept:     {result.skipped}")
        print(f"errors:   {result.errors}")
        for sid in result.removed_ids:
            print(f"  - {sid}")
    return 1 if result.errors and not result.removed else 0


def _cmd_refresh(args: argparse.Namespace) -> None:
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
        force=True,
        group_filter=args.group,
    )
    action = "Would refresh" if args.dry_run else "Refreshed"
    logger.info(
        "{} {} ungraded file(s) from courses {} → {}",
        action,
        count,
        ",".join(str(c) for c in settings.course_ids),
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


def _cmd_schedule_parse(args: argparse.Namespace) -> int:
    path = write_parsed_schedule(args.schedule_dir, html_path=args.html)
    parsed = load_parsed_schedule(args.schedule_dir)
    print(f"wrote:    {path}")
    print(f"teacher:  {parsed.teacher}")
    print(f"entries:  {len(parsed.entries)}")
    print(f"subjects: {', '.join(f'{k}={v}' for k, v in parsed.subjects.items())}")
    return 0


def _cmd_grade_status(args: argparse.Namespace) -> int:
    settings = load_settings()
    root = Path(args.output) if args.output else settings.output_dir
    rec = get_submission(root, args.submission_id)
    if rec is None:
        logger.error("Unknown submission id: {}", args.submission_id)
        return 1
    status = check_grade_status(settings, rec, output_dir=root)
    if args.json:
        print(json.dumps(grade_status_as_dict(status), ensure_ascii=False, indent=2))
    else:
        print(f"submission_id: {status.submission_id}")
        print(f"student:       {status.student_name}")
        print(f"lab:           {status.lab_title} ({status.group})")
        print(f"graded:        {str(status.graded).lower()}")
        print(f"grade:         {status.grade if status.grade is not None else ''}")
    # Exit 0 if graded (skip), 2 if not graded — easy for scripts; always 0 for interactive
    return 0


def _cmd_grade_cap(args: argparse.Namespace) -> int:
    if args.held and args.submitted:
        cap = compute_grade_cap(args.held, args.submitted)
    elif args.submission_id:
        settings = load_settings()
        root = Path(args.output) if args.output else settings.output_dir
        rec = get_submission(root, args.submission_id)
        if rec is None:
            logger.error("Unknown submission id: {}", args.submission_id)
            return 1
        cap = grade_cap_for_submission(
            settings,
            rec,
            subject=args.subject,
            lab_number=args.lab,
            output_dir=root,
        )
    else:
        raise SystemExit("Pass submission_id, or both --held and --submitted")

    payload = grade_cap_as_dict(cap)
    if args.score is not None:
        payload["task_score"] = args.score
        payload["final_score"] = apply_grade_cap(args.score, cap)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"held_on:      {cap.held_on}")
        print(f"submitted_on: {cap.submitted_on}")
        print(f"days_after:   {cap.days_after}")
        print(f"band:         {cap.band}")
        print(f"max_grade:    {cap.max_grade}")
        if args.score is not None:
            print(f"task_score:   {args.score}")
            print(f"final_score:  {payload['final_score']}")
    return 0


def _cmd_held_date(args: argparse.Namespace) -> int:
    subject = args.subject
    lab_number = args.lab
    group = args.group
    if args.submission_id:
        settings = load_settings()
        root = Path(args.output) if args.output else settings.output_dir
        rec = get_submission(root, args.submission_id)
        if rec is None:
            logger.error("Unknown submission id: {}", args.submission_id)
            return 1
        group = group or rec.group
        if lab_number is None:
            lab_number = lab_number_from_title(rec.lab_title)
            if lab_number is None:
                raise SystemExit(
                    f"Could not parse lab number from title {rec.lab_title!r}; pass --lab"
                )
    if not group or lab_number is None:
        raise SystemExit("Need --group and --lab, or a submission_id")

    path = held_path(subject, lab_number, group)
    reused = path.is_file()
    session = ensure_lab_held_date(subject=subject, lab_number=lab_number, group=group)
    if args.json:
        print(json.dumps(asdict(session), ensure_ascii=False, indent=2))
    else:
        print(f"subject:  {session.subject}")
        print(f"lab:      {lab_number}")
        print(f"group:    {session.group}")
        print(f"held_on:  {session.date} ({session.weekday} {session.time})")
        print(f"cached:   {path} ({'reused' if reused else 'wrote'})")
    return 0


def _cmd_submissions(args: argparse.Namespace) -> int:
    settings = load_settings()
    root = Path(args.output) if args.output else settings.output_dir
    if args.reindex:
        records = reindex_from_disk(root)
        logger.info(
            "Indexed {} submission(s) → {}", len(records), root / "submissions.json"
        )
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
