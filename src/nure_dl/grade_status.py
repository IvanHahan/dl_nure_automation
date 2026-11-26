"""Check whether a Moodle assignment submission still needs grading."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup
from loguru import logger

from nure_dl.client import MoodleClient
from nure_dl.comments import ensure_moodle_ids
from nure_dl.grading import grading_url, has_next_page
from nure_dl.index import SubmissionRecord
from nure_dl.settings import Settings

_GRADE_VALUE_RE = re.compile(r'name="grade"[^>]*value="([^"]*)"')
_RESUBMITTED_RE = re.compile(
    r"graded\s*[-–—]?\s*resubmitted|resubmitted", re.IGNORECASE
)
_FINAL_GRADE_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*/\s*\d")

# assign_id -> {user_id: QueueRow}; cleared when the client context ends via new call patterns.
_QUEUE_CACHE: dict[str, dict[str, _QueueRow]] = {}


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

    Prefer the requiregrading table (one fetch per assignment, cached) so a full
    evaluate batch does not hit the grade page for every student.
    """
    root = output_dir if output_dir is not None else settings.output_dir
    with MoodleClient(settings.base_url, settings.session) as client:
        assign_id, user_id = ensure_moodle_ids(client, settings, rec, root)
        queue_map = _requiregrading_index(client, settings.base_url, assign_id)
        queue = queue_map.get(user_id)

        if queue is not None:
            grade = queue.grade
            if grade is None:
                grade = _grade_from_grade_page(client, assign_id, user_id)
            return GradeStatus(
                graded=grade is not None or queue.resubmitted,
                needs_grading=True,
                resubmitted=queue.resubmitted,
                grade=grade,
                assign_id=assign_id,
                moodle_user_id=user_id,
                student_name=rec.student_name,
                lab_title=rec.lab_title,
                group=rec.group,
                submission_id=rec.id,
            )

        # Not in requiregrading → nothing left to grade for evaluate/clean.
        grade = _grade_from_grade_page(client, assign_id, user_id)
        return GradeStatus(
            graded=grade is not None,
            needs_grading=False,
            resubmitted=False,
            grade=grade,
            assign_id=assign_id,
            moodle_user_id=user_id,
            student_name=rec.student_name,
            lab_title=rec.lab_title,
            group=rec.group,
            submission_id=rec.id,
        )


def clear_grade_status_cache() -> None:
    """Drop cached requiregrading tables (call between evaluate batches if needed)."""
    _QUEUE_CACHE.clear()


def grade_status_as_dict(status: GradeStatus) -> dict:
    return asdict(status)


@dataclass(frozen=True)
class _QueueRow:
    resubmitted: bool
    grade: str | None = None


def _requiregrading_index(
    client: MoodleClient,
    base_url: str,
    assign_id: str,
) -> dict[str, _QueueRow]:
    cached = _QUEUE_CACHE.get(assign_id)
    if cached is not None:
        return cached

    rows: dict[str, _QueueRow] = {}
    page = 0
    while True:
        html = client.get_text(grading_url(base_url, assign_id, page=page))
        soup = BeautifulSoup(html, "lxml")
        for tr in soup.select("table.generaltable tr, table.flexible tr"):
            if not tr.select("td"):
                continue
            user_id = _row_user_id(tr)
            if not user_id:
                continue
            status = tr.select_one("td.status")
            text = status.get_text(" ", strip=True) if status is not None else ""
            grade = _row_final_grade(tr)
            rows[user_id] = _QueueRow(
                resubmitted=bool(_RESUBMITTED_RE.search(text)),
                grade=grade,
            )
        if not has_next_page(html):
            break
        page += 1
        if page > 50:
            break

    logger.debug(
        "Cached requiregrading for assign {}: {} student(s)", assign_id, len(rows)
    )
    _QUEUE_CACHE[assign_id] = rows
    return rows


def _grade_from_grade_page(
    client: MoodleClient, assign_id: str, user_id: str
) -> str | None:
    try:
        html = client.get_text(
            f"/mod/assign/view.php?id={assign_id}&action=grade&userid={user_id}"
        )
    except Exception as exc:  # noqa: BLE001 — status check should degrade softly
        logger.warning(
            "Grade page unavailable for assign={} user={}: {}", assign_id, user_id, exc
        )
        return None
    return _read_grade(html)


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


def _row_final_grade(tr) -> str | None:
    # Last cells often hold "0.00 / 100.00" (Final grade).
    for td in reversed(tr.select("td")):
        text = td.get_text(" ", strip=True)
        match = _FINAL_GRADE_RE.search(text)
        if match:
            return match.group(1).replace(",", ".")
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
