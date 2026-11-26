"""Check whether a Moodle assignment submission still needs grading."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from nure_dl.client import MoodleClient
from nure_dl.comments import ensure_moodle_ids
from nure_dl.grading import grading_url, has_next_page
from nure_dl.index import SubmissionRecord
from nure_dl.settings import Settings

_GRADE_VALUE_RE = re.compile(r'name="grade"[^>]*value="([^"]*)"')
_RESUBMITTED_RE = re.compile(
    r"graded\s*[-–—]?\s*resubmitted|resubmitted", re.IGNORECASE
)


@dataclass(frozen=True)
class GradeStatus:
    graded: bool
    needs_grading: bool
    resubmitted: bool
    grade: str | None
    assign_id: str
    moodle_user_id: str
    student_name: str
    lab_title: str
    group: str
    submission_id: str


def check_grade_status(
    settings: Settings,
    rec: SubmissionRecord,
    *,
    output_dir: Path | None = None,
) -> GradeStatus:
    """Report grade value and whether Moodle still lists the work as needing grading.

    Students who resubmit after a grade stay ``graded=True`` but appear again in
    Moodle's ``requiregrading`` queue (status ``Graded - resubmitted``). Those
    must be treated as ``needs_grading=True`` so evaluate/download keep them.
    """
    root = output_dir if output_dir is not None else settings.output_dir
    with MoodleClient(settings.base_url, settings.session) as client:
        assign_id, user_id = ensure_moodle_ids(client, settings, rec, root)
        html = client.get_text(
            f"/mod/assign/view.php?id={assign_id}&action=grade&userid={user_id}"
        )
        grade = _read_grade(html)
        queue = _requiregrading_row(client, settings.base_url, assign_id, user_id)

    needs_grading = queue is not None
    resubmitted = bool(queue and queue.resubmitted)
    return GradeStatus(
        graded=grade is not None,
        needs_grading=needs_grading,
        resubmitted=resubmitted,
        grade=grade,
        assign_id=assign_id,
        moodle_user_id=user_id,
        student_name=rec.student_name,
        lab_title=rec.lab_title,
        group=rec.group,
        submission_id=rec.id,
    )


def grade_status_as_dict(status: GradeStatus) -> dict:
    return asdict(status)


@dataclass(frozen=True)
class _QueueRow:
    resubmitted: bool


def _requiregrading_row(
    client: MoodleClient,
    base_url: str,
    assign_id: str,
    user_id: str,
) -> _QueueRow | None:
    """Return the student's row in the requiregrading table, if present."""
    page = 0
    while True:
        html = client.get_text(grading_url(base_url, assign_id, page=page))
        soup = BeautifulSoup(html, "lxml")
        for tr in soup.select("table.generaltable tr, table.flexible tr"):
            if not tr.select("td"):
                continue
            if _row_user_id(tr) != user_id:
                continue
            status = tr.select_one("td.status")
            text = status.get_text(" ", strip=True) if status is not None else ""
            return _QueueRow(resubmitted=bool(_RESUBMITTED_RE.search(text)))
        if not has_next_page(html):
            return None
        page += 1
        if page > 50:
            return None


def _row_user_id(tr) -> str | None:
    cell = tr.select_one("td.username")
    if cell is None:
        return None
    for anchor in cell.select('a[href*="/user/view.php"]'):
        match = re.search(r"[?&]id=(\d+)", anchor.get("href", ""))
        if match:
            return match.group(1)
    # Moodle also marks rows as user<id>
    for cls in tr.get("class") or []:
        match = re.fullmatch(r"user(\d+)", cls)
        if match:
            return match.group(1)
    return None


def _read_grade(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    field = soup.select_one('input#id_grade, input[name="grade"]')
    if field is not None:
        raw = (field.get("value") or "").strip()
        if raw != "":
            return raw
    current = soup.select_one(".currentgrade")
    if current is not None:
        text = current.get_text(" ", strip=True)
        if (
            text
            and not re.search(r"not\s*graded|не\s*оцінен", text, re.IGNORECASE)
            and re.search(r"\d", text)
        ):
            return text
    match = _GRADE_VALUE_RE.search(html)
    if match and match.group(1).strip():
        return match.group(1).strip()
    # Class marker without a parseable number still counts as graded
    if soup.select_one(".submissiongraded") is not None:
        return "?"
    return None
