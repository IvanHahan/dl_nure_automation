from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    base_url: str
    session: str
    course_ids: tuple[int, ...]
    output_dir: Path


def _parse_course_ids() -> tuple[int, ...]:
    raw = os.getenv("MOODLE_COURSE_IDS", "").strip()
    if raw:
        return tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    single = os.getenv("MOODLE_COURSE_ID", "32388").strip()
    return (int(single),)


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or Path(".env"))
    session = os.getenv("MOODLE_SESSION", "").strip()
    if not session:
        raise SystemExit(
            "MOODLE_SESSION is empty. Copy .env.example → .env and paste "
            "MoodleSession from DevTools."
        )
    course_ids = _parse_course_ids()
    if not course_ids:
        raise SystemExit("Set MOODLE_COURSE_IDS or MOODLE_COURSE_ID in .env")
    return Settings(
        base_url=os.getenv("MOODLE_BASE_URL", "https://dl.nure.ua").rstrip("/"),
        session=session,
        course_ids=course_ids,
        output_dir=Path(os.getenv("MOODLE_OUTPUT_DIR", "downloads")),
    )
