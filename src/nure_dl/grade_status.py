"""Check whether a Moodle assignment submission is already graded."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from nure_dl.client import MoodleClient
from nure_dl.comments import ensure_moodle_ids
from nure_dl.index import SubmissionRecord
from nure_dl.settings import Settings

_GRADE_VALUE_RE = re.compile(r'name="grade"[^>]*value="([^"]*)"')
_CURRENT_GRADE_RE = re.compile(
    r'class="[^"]*currentgrade[^"]*"[^>]*>([^<]+)',
    re.I,
)


@dataclass(frozen=True)
class GradeStatus:
    graded: bool
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
    """Fetch the Moodle grade page and report whether a grade is already set."""
    root = output_dir if output_dir is not None else settings.output_dir
    with MoodleClient(settings.base_url, settings.session) as client:
        assign_id, user_id = ensure_moodle_ids(client, settings, rec, root)
        html = client.get_text(
            f"/mod/assign/view.php?id={assign_id}&action=grade&userid={user_id}"
        )
    grade = _read_grade(html)
    return GradeStatus(
        graded=grade is not None,
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
        if text and not re.search(r"not\s*graded|не\s*оцінен", text, re.I):
            if re.search(r"\d", text):
                return text
    match = _GRADE_VALUE_RE.search(html)
    if match and match.group(1).strip():
        return match.group(1).strip()
    # Class marker without a parseable number still counts as graded
    if soup.select_one(".submissiongraded") is not None:
        return "?"
    return None
