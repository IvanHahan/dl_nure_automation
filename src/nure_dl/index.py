"""Local submission registry — rate by id without searching DL again."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from nure_dl.models import LabAssignment, SubmissionFile

INDEX_NAME = "submissions.json"


@dataclass
class SubmissionRecord:
    id: str
    path: str
    course_id: int
    course_name: str
    group: str
    assign_id: str
    lab_title: str
    student_name: str
    student_email: str
    filename: str
    moodle_user_id: str | None = None
    moodle_file_id: str | None = None
    source_url: str | None = None
    downloaded_at: str | None = None


def index_path(output_dir: Path) -> Path:
    return output_dir / INDEX_NAME


def load_index(output_dir: Path) -> dict[str, SubmissionRecord]:
    path = index_path(output_dir)
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("submissions", raw if isinstance(raw, list) else [])
    out: dict[str, SubmissionRecord] = {}
    for item in items:
        rec = SubmissionRecord(**item)
        out[rec.id] = rec
    return out


def save_index(output_dir: Path, records: dict[str, SubmissionRecord]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = index_path(output_dir)
    payload = {
        "updated_at": _now(),
        "submissions": [asdict(records[k]) for k in sorted(records)],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def make_submission_id(lab: LabAssignment, item: SubmissionFile) -> str:
    if item.moodle_file_id:
        return f"sf-{item.moodle_file_id}"
    email = re.sub(r"[^a-z0-9]+", "-", (item.student_email or "unknown").lower()).strip("-")
    file_key = re.sub(r"[^a-z0-9]+", "-", item.filename.lower()).strip("-")[:40]
    return f"local-{lab.assign_id}-{email}-{file_key}"


def register_submission(
    output_dir: Path,
    lab: LabAssignment,
    item: SubmissionFile,
    dest: Path,
) -> SubmissionRecord:
    records = load_index(output_dir)
    sid = make_submission_id(lab, item)
    rec = SubmissionRecord(
        id=sid,
        path=str(dest.resolve()),
        course_id=lab.course_id,
        course_name=lab.course_name,
        group=lab.group,
        assign_id=lab.assign_id,
        lab_title=lab.title,
        student_name=item.student_name,
        student_email=item.student_email,
        filename=item.filename,
        moodle_user_id=item.moodle_user_id,
        moodle_file_id=item.moodle_file_id,
        source_url=item.url,
        downloaded_at=_now(),
    )
    records[sid] = rec
    save_index(output_dir, records)
    return rec


def get_submission(output_dir: Path, submission_id: str) -> SubmissionRecord | None:
    return load_index(output_dir).get(submission_id)


def reindex_from_disk(output_dir: Path) -> dict[str, SubmissionRecord]:
    """Build/merge index from files already under downloads/ (no Moodle)."""
    root = output_dir.resolve()
    records = load_index(root)
    suffixes = {".pdf", ".docx", ".doc", ".zip"}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        if path.name == INDEX_NAME:
            continue
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        parts = rel.parts
        if len(parts) < 4:
            continue
        course_name, group, lab_title, student = parts[0], parts[1], parts[2], parts[3]
        filename = path.name
        email_guess = ""
        sid = f"local-{_slug(group)}-{_slug(lab_title)}-{_slug(student)}-{_slug(filename)}"
        if sid in records:
            continue
        records[sid] = SubmissionRecord(
            id=sid,
            path=str(path.resolve()),
            course_id=0,
            course_name=course_name,
            group=group,
            assign_id="",
            lab_title=lab_title,
            student_name=student,
            student_email=email_guess,
            filename=filename,
            downloaded_at=_now(),
        )
    save_index(root, records)
    return records


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:48] or "x"


def moodle_file_id_from_url(url: str) -> str | None:
    # .../assignsubmission_file/submission_files/<id>/filename
    path = unquote(urlparse(url).path)
    match = re.search(r"/submission_files/(\d+)/", path)
    return match.group(1) if match else None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
