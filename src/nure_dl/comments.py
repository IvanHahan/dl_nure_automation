"""Post comments to Moodle assign submission comment threads."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup
from loguru import logger

from nure_dl.client import MoodleClient
from nure_dl.course import discover_labs
from nure_dl.index import SubmissionRecord, load_index, save_index
from nure_dl.models import LabAssignment
from nure_dl.settings import Settings

_COMMENT_INIT_RE = re.compile(r"M\.core_comment\.init\(Y,\s*(\{[^}]+\})")
_SESSKEY_RE = re.compile(r'"sesskey":"([^"]+)"')


@dataclass(frozen=True)
class CommentTarget:
    assign_id: str
    moodle_user_id: str
    itemid: int
    contextid: int
    courseid: int
    component: str
    area: str
    client_id: str
    sesskey: str


def post_submission_comment(
    settings: Settings,
    rec: SubmissionRecord,
    content: str,
    *,
    output_dir: Path | None = None,
) -> dict:
    """Post ``content`` to the submission comments area for ``rec`` on DL."""
    text = content.strip()
    if not text:
        raise SystemExit("Comment text is empty.")

    with MoodleClient(settings.base_url, settings.session) as client:
        assign_id, user_id = ensure_moodle_ids(client, settings, rec, output_dir)
        target = load_comment_target(client, assign_id, user_id)
        payload = {
            "sesskey": target.sesskey,
            "action": "add",
            "client_id": target.client_id,
            "itemid": target.itemid,
            "area": target.area,
            "courseid": target.courseid,
            "contextid": target.contextid,
            "component": target.component,
            "content": text,
        }
        response = client.post_form("/comment/comment_ajax.php", payload)
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise SystemExit(
                f"Moodle comment API returned non-JSON: {response.text[:200]!r}"
            ) from exc
        if not isinstance(data, dict) or "id" not in data:
            raise SystemExit(f"Unexpected comment API response: {data!r}")
        logger.info(
            "Posted comment id={} on {} / {} (user {})",
            data["id"],
            rec.lab_title,
            rec.student_name,
            user_id,
        )
        return data


def load_comment_target(
    client: MoodleClient,
    assign_id: str,
    moodle_user_id: str,
) -> CommentTarget:
    html = client.get_text(
        f"/mod/assign/view.php?id={assign_id}&action=grade&userid={moodle_user_id}"
    )
    sesskey_m = _SESSKEY_RE.search(html)
    inits = [json.loads(m.group(1)) for m in _COMMENT_INIT_RE.finditer(html)]
    init = next(
        (c for c in inits if c.get("component") == "assignsubmission_comments"),
        inits[0] if inits else None,
    )
    if sesskey_m is None or init is None:
        raise SystemExit(
            f"Could not find submission comments UI for assign={assign_id} "
            f"user={moodle_user_id}. Check MoodleSession / permissions."
        )
    return CommentTarget(
        assign_id=assign_id,
        moodle_user_id=moodle_user_id,
        itemid=int(init["itemid"]),
        contextid=int(init["contextid"]),
        courseid=int(init["courseid"]),
        component=str(init["component"]),
        area=str(init.get("commentarea") or init.get("area") or "submission_comments"),
        client_id=str(init["client_id"]),
        sesskey=sesskey_m.group(1),
    )


def ensure_moodle_ids(
    client: MoodleClient,
    settings: Settings,
    rec: SubmissionRecord,
    output_dir: Path | None,
) -> tuple[str, str]:
    assign_id = (rec.assign_id or "").strip()
    user_id = (rec.moodle_user_id or "").strip()
    if assign_id and user_id:
        return assign_id, user_id

    logger.info(
        "Index missing assign/user for {} — resolving on DL from group/lab/name…",
        rec.id,
    )
    assign_id, user_id = resolve_assign_and_user(client, settings, rec)
    root = output_dir if output_dir is not None else settings.output_dir
    _persist_moodle_ids(root, rec.id, assign_id, user_id)
    return assign_id, user_id


def resolve_assign_and_user(
    client: MoodleClient,
    settings: Settings,
    rec: SubmissionRecord,
) -> tuple[str, str]:
    labs = _find_matching_labs(client, settings, rec)
    if not labs:
        raise SystemExit(
            f"Could not match lab «{rec.lab_title}» / group «{rec.group}» on DL. "
            "Re-run `download` so submissions.json keeps assign_id."
        )
    needle = _norm_name(rec.student_name)
    for lab in labs:
        user_id = _find_participant_id(client, lab, needle, rec.student_email)
        if user_id is None:
            user_id = _find_user_on_grading(
                client, settings, lab, needle, rec.student_email
            )
        if user_id:
            return lab.assign_id, user_id
    raise SystemExit(
        f"Could not find student «{rec.student_name}» on grading tables for "
        f"«{rec.lab_title}». Re-run `download` or check the name on DL."
    )


def _find_matching_labs(
    client: MoodleClient,
    settings: Settings,
    rec: SubmissionRecord,
) -> list[LabAssignment]:
    title_n = _norm_name(rec.lab_title)
    group_n = _norm_name(rec.group)
    course_n = _norm_name(rec.course_name)
    by_group_title: list[LabAssignment] = []
    preferred: list[LabAssignment] = []
    for course_id in settings.course_ids:
        labs, fullname, shortname = discover_labs(client, course_id)
        for lab in labs:
            if group_n and _norm_name(lab.group) != group_n:
                continue
            if title_n and _norm_name(lab.title) != title_n:
                continue
            by_group_title.append(lab)
            course_keys = {
                _norm_name(lab.course_name),
                _norm_name(fullname or ""),
                _norm_name(shortname or ""),
                str(course_id),
            }
            if (
                not course_n
                or course_n in course_keys
                or any(course_n in key for key in course_keys if key)
            ):
                preferred.append(lab)
    return preferred or by_group_title


def _find_participant_id(
    client: MoodleClient,
    lab: LabAssignment,
    student_name_n: str,
    student_email: str,
) -> str | None:
    email_n = (student_email or "").casefold().strip()
    matches: set[str] = set()
    for participant in client.get_assignment_participants(lab.assign_id):
        user_id = str(participant.get("id"))
        if not user_id.isdecimal() or int(user_id) == 0:
            continue
        if email_n:
            matches_email = (
                participant.get("email") or ""
            ).casefold().strip() == email_n
            if matches_email:
                matches.add(user_id)
        elif (
            student_name_n
            and _norm_name(participant.get("fullname") or "") == student_name_n
        ):
            matches.add(user_id)
    return next(iter(matches)) if len(matches) == 1 else None


def _find_user_on_grading(
    client: MoodleClient,
    settings: Settings,
    lab: LabAssignment,
    student_name_n: str,
    student_email: str,
) -> str | None:
    email_n = (student_email or "").casefold().strip()
    page = 0
    while page <= 50:
        url = (
            f"{settings.base_url.rstrip('/')}/mod/assign/view.php"
            f"?id={lab.assign_id}&action=grading&perpage=100&page={page}"
        )
        html = client.get_text(url)
        soup = BeautifulSoup(html, "lxml")
        table = soup.select_one("table.generaltable") or soup.select_one(
            "table.flexible"
        )
        if table is None:
            return None
        for tr in table.select("tr"):
            if not tr.select("td"):
                continue
            uid = _row_user_id(tr)
            if not uid:
                continue
            name = _row_student_name(tr)
            email_el = tr.select_one("td.email")
            email = email_el.get_text(" ", strip=True) if email_el else ""
            if email_n and email.casefold().strip() == email_n:
                return uid
            if student_name_n and _norm_name(name) == student_name_n:
                return uid
        if not _has_next_grading_page(html):
            break
        page += 1
    return None


def _persist_moodle_ids(
    output_dir: Path,
    submission_id: str,
    assign_id: str,
    user_id: str,
) -> None:
    records = load_index(output_dir)
    rec = records.get(submission_id)
    if rec is None:
        return
    rec.assign_id = assign_id
    rec.moodle_user_id = user_id
    save_index(output_dir, records)
    logger.info(
        "Updated index {} with assign={} user={}", submission_id, assign_id, user_id
    )


def _row_user_id(tr) -> str | None:
    cell = tr.select_one("td.username")
    if cell is None:
        return None
    for anchor in cell.select('a[href*="/user/view.php"]'):
        match = re.search(r"[?&]id=(\d+)", anchor.get("href", ""))
        if match:
            return match.group(1)
    return None


def _row_student_name(tr) -> str:
    cell = tr.select_one("td.username")
    if cell is None:
        return ""
    initials = cell.select_one(".userinitials")
    if initials is not None:
        for attr in ("title", "aria-label"):
            label = (initials.get(attr) or "").strip()
            if label:
                return label
    for anchor in cell.select('a[href*="/user/view.php"]'):
        for span in anchor.select(".userinitials"):
            span.extract()
        text = anchor.get_text(" ", strip=True)
        if text:
            return text
    return cell.get_text(" ", strip=True)


def _has_next_grading_page(html: str) -> bool:
    return any(
        a.get_text(strip=True) in {"Next", "Наступна", "»"}
        for a in BeautifulSoup(html, "lxml").select("a[href*='action=grading']")
    )


def _norm_name(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").casefold().strip())
