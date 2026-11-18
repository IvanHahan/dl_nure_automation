from __future__ import annotations

import re
from pathlib import Path

from loguru import logger

from nure_dl.client import MoodleClient
from nure_dl.course import (
    parse_course_fullname,
    parse_course_shortname_from_assign,
    parse_lab_assignments,
    resolve_course_name,
)
from nure_dl.grading import grading_url, has_next_page, parse_ungraded_files
from nure_dl.index import register_submission
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
    html = client.get_text(f"/course/view.php?id={course_id}")
    fullname = parse_course_fullname(html)
    # Shortname distinguishes streams that share a similar full name on DL
    shortname = None
    preview = parse_lab_assignments(html, settings.base_url, course_id, "pending")
    if preview:
        assign_html = client.get_text(f"/mod/assign/view.php?id={preview[0].assign_id}")
        shortname = parse_course_shortname_from_assign(assign_html)
    course_name = resolve_course_name(fullname, shortname, course_id)
    labs = parse_lab_assignments(html, settings.base_url, course_id, course_name)
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
                    if exists and not force:
                        logger.debug("Skip existing {}", dest)
                    else:
                        client.download(item.url, dest)
                        logger.info(
                            "{} {}",
                            "Re-downloaded" if exists else "Downloaded",
                            dest,
                        )
                        downloaded += 1
                    rec = register_submission(settings.output_dir, lab, item, dest)
                    logger.info("Indexed {} → {}", rec.id, dest)
    return downloaded


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
