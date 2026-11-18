"""Resolve a cached submission and prepare it for grading (any lab)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from nure_dl.dump import dump_report
from nure_dl.index import SubmissionRecord, get_submission, load_index


@dataclass
class GradePrep:
    submission: SubmissionRecord
    dump_dir: Path
    grades_path: Path


def prepare_grade(
    output_dir: Path,
    submission_id: str,
    *,
    dump_root: Path | None = None,
) -> GradePrep:
    """Look up submission by id and dump the report for reading. No lab-specific logic."""
    rec = get_submission(output_dir, submission_id)
    if rec is None:
        known = ", ".join(sorted(load_index(output_dir))[:8]) or "(empty index)"
        raise SystemExit(
            f"Unknown submission id {submission_id!r}. "
            f"See `python -m nure_dl submissions`. Examples: {known}"
        )
    src = Path(rec.path)
    if not src.is_file():
        raise SystemExit(f"Indexed file missing on disk: {src}")

    dump_root = dump_root or (output_dir / "_grade_dumps")
    dump_dir = dump_report(src, dump_root)
    grades_path = output_dir / "grades.json"
    logger.info("Prepared {} → {}", submission_id, dump_dir)
    return GradePrep(submission=rec, dump_dir=dump_dir, grades_path=grades_path)


def save_grade_result(
    output_dir: Path,
    submission_id: str,
    *,
    tasks: list[dict],
    summary: str | None = None,
    score: float | int | str | None = None,
) -> Path:
    """Persist a grade result for any submission (structure is caller-defined)."""
    path = output_dir / "grades.json"
    data: dict
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"grades": {}}
    rec = get_submission(output_dir, submission_id)
    data.setdefault("grades", {})[submission_id] = {
        "submission_id": submission_id,
        "path": rec.path if rec else None,
        "student_name": rec.student_name if rec else None,
        "lab_title": rec.lab_title if rec else None,
        "group": rec.group if rec else None,
        "graded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "score": score,
        "summary": summary,
        "tasks": tasks,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def print_prep(prep: GradePrep) -> None:
    rec = prep.submission
    print(f"submission_id: {rec.id}")
    print(f"student:       {rec.student_name} <{rec.student_email}>")
    print(f"lab:           {rec.lab_title} ({rec.group})")
    print(f"file:          {rec.path}")
    print(f"dump:          {prep.dump_dir}")
    print(f"text:          {prep.dump_dir / 'text.txt'}")
    print(f"images:        {prep.dump_dir / 'images'}")
    print(f"grades_file:   {prep.grades_path}")
    print()
    print("Next: evaluate with nure-lab-evaluate + guidelines/<subject>/labs/, then -s SCORE -c …")
