"""Remove local copies of submissions that are already graded on Moodle."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from loguru import logger

from nure_dl.dump import dump_dir_for
from nure_dl.grade_status import check_grade_status
from nure_dl.index import INDEX_NAME, SubmissionRecord, load_index, save_index
from nure_dl.schedule import lab_number_from_title
from nure_dl.settings import Settings


@dataclass(frozen=True)
class CleanResult:
    checked: int
    graded: int
    removed: int
    skipped: int
    errors: int
    removed_ids: tuple[str, ...]
    dry_run: bool


def clean_graded_submissions(
    settings: Settings,
    *,
    output_dir: Path | None = None,
    group_filter: str | None = None,
    lab_filter: int | None = None,
    dry_run: bool = False,
) -> CleanResult:
    """Check Moodle grade status for each indexed file; delete graded locals."""
    root = (output_dir or settings.output_dir).resolve()
    records = load_index(root)
    candidates = [
        rec
        for rec in records.values()
        if _matches_filters(rec, group_filter=group_filter, lab_filter=lab_filter)
    ]
    removed_ids: list[str] = []
    graded = 0
    skipped = 0
    errors = 0

    for rec in sorted(candidates, key=lambda r: r.id):
        try:
            status = check_grade_status(settings, rec, output_dir=root)
        except Exception as exc:  # noqa: BLE001 — continue batch on one bad id
            errors += 1
            logger.error("grade-status failed for {}: {}", rec.id, exc)
            continue
        if not status.graded:
            skipped += 1
            logger.debug("Keep ungraded {} ({})", rec.id, rec.student_name)
            continue
        graded += 1
        logger.info(
            "Graded on Moodle ({}): {} — {} / {}",
            status.grade,
            rec.id,
            rec.student_name,
            rec.lab_title,
        )
        if dry_run:
            removed_ids.append(rec.id)
            continue
        _remove_local(root, rec)
        records.pop(rec.id, None)
        _drop_grades_entry(root, rec.id)
        removed_ids.append(rec.id)

    if not dry_run and removed_ids:
        save_index(root, records)
        _prune_empty_dirs(root)

    return CleanResult(
        checked=len(candidates),
        graded=graded,
        removed=len(removed_ids),
        skipped=skipped,
        errors=errors,
        removed_ids=tuple(removed_ids),
        dry_run=dry_run,
    )


def clean_result_as_dict(result: CleanResult) -> dict:
    return asdict(result)


def _matches_filters(
    rec: SubmissionRecord,
    *,
    group_filter: str | None,
    lab_filter: int | None,
) -> bool:
    if group_filter and group_filter.casefold() not in rec.group.casefold():
        return False
    if lab_filter is not None:
        number = lab_number_from_title(rec.lab_title)
        if number != lab_filter:
            return False
    return True


def _remove_local(root: Path, rec: SubmissionRecord) -> None:
    path = Path(rec.path)
    if path.is_file():
        path.unlink()
        logger.info("Deleted {}", path)
    else:
        logger.warning("Missing on disk: {}", path)

    dump_dir = dump_dir_for(path, root / "_grade_dumps")
    if dump_dir.is_dir():
        shutil.rmtree(dump_dir)
        logger.info("Deleted dump {}", dump_dir)


def _drop_grades_entry(root: Path, submission_id: str) -> None:
    path = root / "grades.json"
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    grades = data.get("grades")
    if not isinstance(grades, dict) or submission_id not in grades:
        return
    del grades[submission_id]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _prune_empty_dirs(root: Path) -> None:
    """Remove empty student/lab/group folders under downloads/ (keep index files)."""
    keep_names = {INDEX_NAME, "grades.json", "_grade_dumps"}
    for path in sorted(root.rglob("*"), reverse=True):
        if not path.is_dir():
            continue
        if path == root or path.name in keep_names:
            continue
        try:
            next(path.iterdir())
        except StopIteration:
            path.rmdir()
            logger.debug("Removed empty dir {}", path)
