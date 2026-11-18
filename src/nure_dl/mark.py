"""Submit numeric grades to Moodle assign gradebook."""

from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup
from loguru import logger

from nure_dl.client import MoodleClient
from nure_dl.comments import ensure_moodle_ids
from nure_dl.index import SubmissionRecord
from nure_dl.settings import Settings

_GRADE_VALUE_RE = re.compile(r'name="grade"[^>]*value="([^"]*)"')


def submit_assignment_grade(
    settings: Settings,
    rec: SubmissionRecord,
    score: float | int | str,
    *,
    output_dir: Path | None = None,
    notify_student: bool = False,
) -> str:
    """Set the Moodle assignment grade for ``rec``. Returns the grade as stored on DL."""
    grade_text = _format_grade(score)
    root = output_dir if output_dir is not None else settings.output_dir

    with MoodleClient(settings.base_url, settings.session) as client:
        assign_id, user_id = ensure_moodle_ids(client, settings, rec, root)
        grade_url = (
            f"/mod/assign/view.php?id={assign_id}&action=grade&userid={user_id}"
        )
        html = client.get_text(grade_url)
        data = _grade_form_payload(html, grade_text, notify_student=notify_student)
        response = client.post_form(
            "/mod/assign/view.php",
            data,
            referer=f"{settings.base_url}{grade_url}",
            allow_login_redirect=True,
        )
        if "/login/index.php" in str(response.url) and not any(
            "action=savegradingresult" in str(h.url) for h in response.history
        ):
            raise SystemExit(
                "Redirected to login while saving grade — MoodleSession expired. "
                "Refresh .env from DevTools."
            )

        verify = client.get_text(grade_url)
        stored = _read_grade_value(verify)
        if stored is None:
            raise SystemExit("Grade submit finished but could not read grade field back.")
        # Moodle stores "70.00"; compare numerically
        if abs(float(stored) - float(grade_text)) > 0.001:
            raise SystemExit(
                f"Grade submit may have failed: wanted {grade_text}, DL shows {stored}"
            )
        logger.info(
            "Graded {} / {} → {} (assign={} user={})",
            rec.lab_title,
            rec.student_name,
            stored,
            assign_id,
            user_id,
        )
        return stored


def _format_grade(score: float | int | str) -> str:
    text = str(score).strip().replace(",", ".")
    if not text:
        raise SystemExit("Grade score is empty.")
    try:
        value = float(text)
    except ValueError as exc:
        raise SystemExit(f"Invalid grade score: {score!r}") from exc
    if value < 0:
        raise SystemExit(f"Grade score must be ≥ 0, got {value}")
    # Moodle simple grade accepts decimals; keep compact ints as ints
    if value == int(value):
        return str(int(value))
    return str(value)


def _grade_form_payload(
    html: str,
    grade_text: str,
    *,
    notify_student: bool,
) -> dict[str, str | int]:
    soup = BeautifulSoup(html, "lxml")
    form = next(
        (
            f
            for f in soup.select("form")
            if f.select_one('input[name="grade"]')
            and f.select_one('input[name="action"][value="submitgrade"]')
        ),
        None,
    )
    if form is None:
        raise SystemExit("Could not find Moodle grade form on assign grade page.")

    data: dict[str, str | int] = {}
    for el in form.select("input, textarea, select"):
        name = el.get("name")
        if not name or el.get("type") in {"submit", "button", "image"}:
            continue
        if el.name == "select":
            opt = el.select_one("option[selected]") or el.select_one("option")
            data[name] = opt.get("value", "") if opt else ""
        elif el.get("type") == "checkbox":
            if name == "sendstudentnotifications":
                continue
            if el.has_attr("checked"):
                data[name] = el.get("value", "1")
        elif el.get("type") == "radio":
            if el.has_attr("checked"):
                data[name] = el.get("value", "")
        elif el.name == "textarea":
            data[name] = el.get_text()
        else:
            data[name] = el.get("value") or ""

    data["grade"] = grade_text
    data["action"] = "submitgrade"
    data["savegrade"] = "Save changes"
    if notify_student:
        data["sendstudentnotifications"] = "1"
    else:
        data.pop("sendstudentnotifications", None)
    return data


def _read_grade_value(html: str) -> str | None:
    match = _GRADE_VALUE_RE.search(html)
    if match:
        return match.group(1)
    soup = BeautifulSoup(html, "lxml")
    el = soup.select_one('input#id_grade, input[name="grade"]')
    if el is None:
        return None
    return el.get("value")
