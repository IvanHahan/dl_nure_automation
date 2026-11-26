from __future__ import annotations

import re
from pathlib import Path

from loguru import logger

from nure_dl.client import MoodleClient
from nure_dl.course import discover_labs, resolve_course_name
from nure_dl.grading import grading_url, has_next_page, parse_ungraded_files
from nure_dl.index import (
    load_index,
    make_submission_id,
    register_submission,
    save_index,
)
from nure_dl.models import LabAssignment, SubmissionFile
from nure_dl.schedule import group_on_schedule, schedule_group_names
from nure_dl.settings import Settings

# Allow ":" so Moodle shortnames stay readable; still block path separators.
_UNSAFE = re.compile(r'[<>"/\\|?*\x00-\x1f]+')


def safe_name(value: str, fallback: str = "item") -> str:
    cleaned = _UNSAFE.sub("_", value).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:120] or fallback


def list_labs(
    client: MoodleClient,
    settings: Settings,
    course_id: int,
) -> list[LabAssignment]:
    labs, fullname, shortname = discover_labs(client, course_id)
    course_name = resolve_course_name(fullname, shortname, course_id)
    logger.info(
        "Found {} lab assignments on «{}» (id={})",
        len(labs),
        course_name,
        course_id,
    )
    return labs


def collect_ungraded(
    client: MoodleClient,
    settings: Settings,
    lab: LabAssignment,
) -> list[SubmissionFile]:
    files: list[SubmissionFile] = []
    page = 0
    while True:
        url = grading_url(settings.base_url, lab.assign_id, page=page)
        html = client.get_text(url)
        batch = parse_ungraded_files(html, settings.base_url)
        files.extend(batch)
        if not batch or not has_next_page(html):
            break
        page += 1
        if page > 50:
            logger.warning("Stopped pagination at page 50 for assign {}", lab.assign_id)
            break
    return files


def download_ungraded(
    settings: Settings,
    *,
    dry_run: bool = False,
    force: bool = False,
    group_filter: str | None = None,
    course_ids: tuple[int, ...] | None = None,
    respect_schedule: bool = True,
) -> int:
    """Download Moodle ungraded submission files into the local cache.

    When ``force`` is true, existing local files are re-downloaded (refresh).
    By default only groups that appear on the teacher's parsed schedule are
    downloaded (other teachers' groups are skipped).
    """
    downloaded = 0
    targets = course_ids or settings.course_ids
    scheduled: list[str] | None = None
    if respect_schedule:
        scheduled = schedule_group_names()
        if not scheduled:
            raise SystemExit(
                "Parsed schedule has no groups — run "
                "`python -m nure_dl schedule-parse` first, or pass --all-groups."
            )
        logger.info(
            "Schedule filter on: {} group(s) ({})",
            len(scheduled),
            ", ".join(scheduled),
        )

    with MoodleClient(settings.base_url, settings.session) as client:
        for course_id in targets:
            labs = list_labs(client, settings, course_id)
            if group_filter:
                needle = group_filter.casefold()
                labs = [lab for lab in labs if needle in lab.group.casefold()]
                logger.info(
                    "«{}» after group filter {!r}: {} labs",
                    labs[0].course_name if labs else course_id,
                    group_filter,
                    len(labs),
                )
            if respect_schedule:
                kept: list[LabAssignment] = []
                skipped_groups: set[str] = set()
                for lab in labs:
                    if group_on_schedule(lab.group):
                        kept.append(lab)
                    else:
                        skipped_groups.add(lab.group)
                if skipped_groups:
                    logger.info(
                        "Skipping {} group(s) not on schedule: {}",
                        len(skipped_groups),
                        ", ".join(sorted(skipped_groups)),
                    )
                labs = kept

            for lab in labs:
                files = collect_ungraded(client, settings, lab)
                logger.info(
                    "[{}] {} / {} — {} ungraded file(s)",
                    lab.course_name,
                    lab.group,
                    lab.title,
                    len(files),
                )
                for item in files:
                    dest = _destination(settings.output_dir, lab, item)
                    if dry_run:
                        logger.info("DRY-RUN {}", dest)
                        downloaded += 1
                        continue
                    exists = dest.exists() and dest.stat().st_size > 0
                    stale = _is_stale_local(settings.output_dir, lab, item, dest)
                    if exists and not force and not stale:
                        logger.debug("Skip existing {}", dest)
                    else:
                        client.download(item.url, dest)
                        logger.info(
                            "{} {}",
                            "Re-downloaded" if exists or stale else "Downloaded",
                            dest,
                        )
                        downloaded += 1
                    _drop_stale_index_entries(settings.output_dir, lab, item, dest)
                    rec = register_submission(settings.output_dir, lab, item, dest)
                    logger.info("Indexed {} → {}", rec.id, dest)
    return downloaded


def _is_stale_local(
    output_dir: Path,
    lab: LabAssignment,
    item: SubmissionFile,
    dest: Path,
) -> bool:
    """True when a local file exists but Moodle has a newer submission file id."""
    if not item.moodle_file_id:
        return False
    dest = dest.resolve()
    for rec in load_index(output_dir).values():
        same_path = Path(rec.path).resolve() == dest
        same_student = (
            rec.assign_id == lab.assign_id
            and bool(rec.moodle_user_id)
            and rec.moodle_user_id == item.moodle_user_id
        )
        if not (same_path or same_student):
            continue
        if rec.moodle_file_id and rec.moodle_file_id != item.moodle_file_id:
            logger.info(
                "Resubmit detected for {} (file {} → {})",
                item.student_name,
                rec.moodle_file_id,
                item.moodle_file_id,
            )
            return True
    return False


def _drop_stale_index_entries(
    output_dir: Path,
    lab: LabAssignment,
    item: SubmissionFile,
    dest: Path,
) -> None:
    """Remove older index ids for the same student/path after a resubmit."""
    new_id = make_submission_id(lab, item)
    records = load_index(output_dir)
    dest = dest.resolve()
    removed = False
    for sid, rec in list(records.items()):
        if sid == new_id:
            continue
        same_path = Path(rec.path).resolve() == dest
        same_student = (
            rec.assign_id == lab.assign_id
            and bool(rec.moodle_user_id)
            and rec.moodle_user_id == item.moodle_user_id
        )
        if same_path or same_student:
            records.pop(sid)
            removed = True
            logger.info("Dropped stale index entry {}", sid)
    if removed:
        save_index(output_dir, records)


def _destination(root: Path, lab: LabAssignment, item: SubmissionFile) -> Path:
    student = safe_name(item.student_name) or safe_name(
        item.student_email.split("@")[0], "student"
    )
    return (
        root
        / safe_name(lab.course_name, str(lab.course_id))
        / safe_name(lab.group, "group")
        / safe_name(lab.title, f"assign-{lab.assign_id}")
        / student
        / safe_name(item.filename, "submission.bin")
    )
