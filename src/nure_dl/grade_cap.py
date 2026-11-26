"""Max grade by how late the submission is relative to the lab held-on date.

Rules (calendar days after held-on date):

- within 2 weeks (≤ 14 days) → max 100
- 2–6 weeks (15–42 days) → max 90
- later (> 42 days) → max 80

For resubmits, lateness uses the **first** Moodle submission date (not the
latest upload), so fixing a grade does not worsen the cap.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

from bs4 import BeautifulSoup
from loguru import logger

from nure_dl.client import MoodleClient
from nure_dl.comments import ensure_moodle_ids
from nure_dl.index import SubmissionRecord
from nure_dl.schedule import ensure_lab_held_date, lab_number_from_title
from nure_dl.settings import Settings

WITHIN_2_WEEKS_DAYS = 14
WITHIN_6_WEEKS_DAYS = 42

_MOODLE_FILE_TIME_RE = re.compile(
    r"^(\d{1,2})\s+([A-Za-zА-Яа-яІіЇїЄєҐґ]+)\s+(\d{4}),\s*"
    r"(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?$",
    re.IGNORECASE,
)

# Moodle log event names (EN/UK) that mark a student submitting work.
_FIRST_SUBMIT_EVENT_RE = re.compile(
    r"submission has been submitted|"
    r"submission created|"
    r"подання\s+було\s+надіслано|"
    r"створено\s+подання|"
    r"здавання\s+було\s+надіслано",
    re.IGNORECASE,
)

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "січня": 1,
    "лютого": 2,
    "березня": 3,
    "квітня": 4,
    "травня": 5,
    "червня": 6,
    "липня": 7,
    "серпня": 8,
    "вересня": 9,
    "жовтня": 10,
    "листопада": 11,
    "грудня": 12,
}


@dataclass(frozen=True)
class GradeCap:
    held_on: str
    submitted_on: str
    days_after: int
    max_grade: int
    band: str
    submitted_source: str = "first_submission"


def max_grade_for_delay(days_after: int) -> tuple[int, str]:
    """Return (max_grade, band_label) for days after the lab held-on date."""
    if days_after <= WITHIN_2_WEEKS_DAYS:
        return 100, "within_2_weeks"
    if days_after <= WITHIN_6_WEEKS_DAYS:
        return 90, "weeks_2_to_6"
    return 80, "after_6_weeks"


def compute_grade_cap(
    held_on: date | str,
    submitted_on: date | str,
    *,
    submitted_source: str = "first_submission",
) -> GradeCap:
    held = _as_date(held_on)
    submitted = _as_date(submitted_on)
    days_after = (submitted - held).days
    max_grade, band = max_grade_for_delay(days_after)
    return GradeCap(
        held_on=held.isoformat(),
        submitted_on=submitted.isoformat(),
        days_after=days_after,
        max_grade=max_grade,
        band=band,
        submitted_source=submitted_source,
    )


def apply_grade_cap(task_score: float, cap: GradeCap) -> int:
    """Clamp a guidelines task score to the lateness max."""
    return int(min(int(task_score), cap.max_grade))


def grade_cap_for_submission(
    settings: Settings,
    rec: SubmissionRecord,
    *,
    subject: str = "tpks",
    lab_number: int | None = None,
    output_dir: Path | None = None,
) -> GradeCap:
    """Resolve held-on + first Moodle submission date, then compute the cap."""
    root = output_dir if output_dir is not None else settings.output_dir
    number = lab_number or lab_number_from_title(rec.lab_title)
    if number is None:
        raise SystemExit(
            f"Could not parse lab number from {rec.lab_title!r}; pass --lab"
        )
    held = ensure_lab_held_date(subject=subject, lab_number=number, group=rec.group)
    submitted, source = fetch_first_submission_date(settings, rec, output_dir=root)
    return compute_grade_cap(held.date, submitted, submitted_source=source)


def fetch_first_submission_date(
    settings: Settings,
    rec: SubmissionRecord,
    *,
    output_dir: Path | None = None,
) -> tuple[date, str]:
    """Return (date, source) for the student's first submission of this assign.

    Prefers the earliest Moodle log event for submit/create. Falls back to the
    current file upload time on the grade page when logs are unavailable.
    """
    root = output_dir if output_dir is not None else settings.output_dir
    with MoodleClient(settings.base_url, settings.session) as client:
        assign_id, user_id = ensure_moodle_ids(client, settings, rec, root)
        first = _first_submission_from_logs(
            client,
            course_id=rec.course_id,
            assign_id=assign_id,
            user_id=user_id,
        )
        if first is not None:
            logger.info(
                "First submission for {} / {} → {} (logs)",
                rec.student_name,
                rec.lab_title,
                first.date().isoformat(),
            )
            return first.date(), "first_submission_log"

        html = client.get_text(
            f"/mod/assign/view.php?id={assign_id}&action=grade&userid={user_id}"
        )
    stamp = _parse_moodle_submission_time(html)
    if stamp is None:
        raise SystemExit(
            f"Could not find submission time on Moodle "
            f"(assign={assign_id} user={user_id})."
        )
    logger.warning(
        "No submit log for {} / {}; using current file time {}",
        rec.student_name,
        rec.lab_title,
        stamp.date().isoformat(),
    )
    return stamp.date(), "current_file_time"


# Back-compat alias used by older callers / tests
def fetch_submission_date(
    settings: Settings,
    rec: SubmissionRecord,
    *,
    output_dir: Path | None = None,
) -> date:
    submitted, _source = fetch_first_submission_date(
        settings, rec, output_dir=output_dir
    )
    return submitted


def _first_submission_from_logs(
    client: MoodleClient,
    *,
    course_id: int,
    assign_id: str,
    user_id: str,
) -> datetime | None:
    if not course_id:
        return None
    html = client.get_text(
        f"/report/log/index.php?id={course_id}&user={user_id}"
        f"&modid={assign_id}&chooselog=1&logformat=showashtml"
    )
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.generaltable")
    if table is None:
        return None
    earliest: datetime | None = None
    for tr in table.select("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.select("td")]
        if len(cells) < 6:
            continue
        event_name = cells[5]
        if not _FIRST_SUBMIT_EVENT_RE.search(event_name):
            continue
        stamp = _parse_moodle_datetime(cells[0])
        if stamp is None:
            continue
        if earliest is None or stamp < earliest:
            earliest = stamp
    return earliest


def _parse_moodle_submission_time(html: str) -> datetime | None:
    soup = BeautifulSoup(html, "lxml")
    el = soup.select_one(".fileuploadsubmissiontime")
    if el is None:
        return None
    text = el.get_text(" ", strip=True)
    return _parse_moodle_datetime(text)


def _parse_moodle_datetime(text: str) -> datetime | None:
    text = re.sub(r"\s+", " ", text.strip())
    match = _MOODLE_FILE_TIME_RE.match(text)
    if not match:
        return None
    day = int(match.group(1))
    month_name = match.group(2).casefold()
    year = int(match.group(3))
    hour = int(match.group(4))
    minute = int(match.group(5))
    second = int(match.group(6) or 0)
    ampm = (match.group(7) or "").upper()
    month = _MONTHS.get(month_name)
    if month is None:
        return None
    if ampm == "PM" and hour < 12:
        hour += 12
    if ampm == "AM" and hour == 12:
        hour = 0
    return datetime(year, month, day, hour, minute, second)


def _as_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    text = value.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return date.fromisoformat(text)
    # dd.mm.yyyy
    match = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", text)
    if match:
        return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    raise SystemExit(f"Invalid date {value!r}; use YYYY-MM-DD or dd.mm.yyyy")


def grade_cap_as_dict(cap: GradeCap) -> dict:
    return asdict(cap)
