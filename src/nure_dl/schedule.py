"""Parse the teacher schedule HTML into structured JSON, then query lab dates.

Schedule format (I@S «Расписание на преподавателей») is fixed:

- Main grid table: week-number header; per weekday a date row
  ``Понеділок | dd.mm.yyyy | …`` then pair rows ``N | HH:MM HH:MM | cell…``
- Occupied cells: ``{SUBJECT} {KIND} {MODE} {GROUPS}``
  e.g. ``ТПКС Лб DL КІУКІ-24-3`` or ``ТПКС Лб DL КІУКІи-23-1;КІУКІ-23-1``
- Legend table maps subject codes (ТПКС, ПМН, …) to full names

Workflow: ``parse`` → ``local/schedule/parsed.json`` → lookups / held-date cache.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

from bs4 import BeautifulSoup
from loguru import logger

SCHEDULE_DIR = Path("local/schedule")
PARSED_NAME = "parsed.json"

_DAY_NAMES = (
    "Понеділок",
    "Вівторок",
    "Середа",
    "Четвер",
    "П'ятниця",
    "Субота",
    "Неділя",
)

# guidelines/<slug>/ ↔ schedule subject code
SUBJECT_SLUGS = {
    "tpks": "ТПКС",
    "тпкс": "ТПКС",
    "pmn": "ПМН",
    "пмн": "ПМН",
}

_CELL_RE = re.compile(
    r"^(?P<subject>\S+)\s+(?P<kind>Лб|Лк|Зал)\s+(?P<mode>\S+)\s+(?P<groups>.+)$"
)


@dataclass(frozen=True)
class ScheduleEntry:
    date: str
    weekday: str
    week: int
    pair: int
    time: str
    subject: str
    kind: str
    mode: str
    groups: list[str]
    raw: str


@dataclass(frozen=True)
class ParsedSchedule:
    teacher: str
    source: str
    subjects: dict[str, str]
    entries: list[ScheduleEntry]


@dataclass(frozen=True)
class LabSession:
    date: str
    weekday: str
    time: str
    group: str
    subject: str
    cell: str
    source: str
    week: int | None = None
    pair: int | None = None


def parsed_path(schedule_dir: Path | None = None) -> Path:
    return (schedule_dir or SCHEDULE_DIR) / PARSED_NAME


def parse_schedule_html(path: Path) -> ParsedSchedule:
    """Parse one I@S teacher-schedule HTML file into structured entries."""
    html = _read_html(path)
    soup = BeautifulSoup(html, "lxml")
    teacher = _parse_teacher(soup)
    subjects = _parse_legend(soup)
    tables = soup.select("table")
    if len(tables) < 2:
        raise SystemExit(f"Schedule grid table not found in {path}")
    entries = _parse_grid(tables[1])
    return ParsedSchedule(
        teacher=teacher,
        source=str(path.resolve()),
        subjects=subjects,
        entries=entries,
    )


def write_parsed_schedule(
    schedule_dir: Path | None = None,
    *,
    html_path: Path | None = None,
) -> Path:
    """Parse HTML under ``local/schedule/`` and write ``parsed.json``."""
    root = schedule_dir or SCHEDULE_DIR
    root.mkdir(parents=True, exist_ok=True)
    src = html_path or _find_html(root)
    parsed = parse_schedule_html(src)
    out = parsed_path(root)
    payload = {
        "teacher": parsed.teacher,
        "source": parsed.source,
        "subjects": parsed.subjects,
        "entries": [asdict(e) for e in parsed.entries],
        "parsed_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logger.info(
        "Parsed {} → {} ({} entries, teacher={})",
        src.name,
        out,
        len(parsed.entries),
        parsed.teacher or "?",
    )
    return out


def load_parsed_schedule(
    schedule_dir: Path | None = None,
    *,
    rebuild: bool = False,
) -> ParsedSchedule:
    """Load ``parsed.json``, building it from HTML when missing (or ``rebuild``)."""
    root = schedule_dir or SCHEDULE_DIR
    path = parsed_path(root)
    if rebuild or not path.is_file():
        write_parsed_schedule(root)
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = [ScheduleEntry(**e) for e in raw.get("entries", [])]
    return ParsedSchedule(
        teacher=raw.get("teacher", ""),
        source=raw.get("source", str(path)),
        subjects=dict(raw.get("subjects") or {}),
        entries=entries,
    )


def held_path(subject: str, lab_number: int, group: str) -> Path:
    return (
        Path("guidelines")
        / _subject_slug(subject)
        / "labs"
        / f"lab-{lab_number}"
        / "held"
        / f"{_group_slug(group)}.json"
    )


def ensure_lab_held_date(
    *,
    subject: str,
    lab_number: int,
    group: str,
    schedule_dir: Path | None = None,
) -> LabSession:
    """
    Return when lab N was held for ``group``.

    Reuses ``guidelines/<subject>/labs/lab-N/held/<group>.json`` when present;
    otherwise queries the parsed schedule (Lab N = N-th Лб session) and writes it.
    """
    path = held_path(subject, lab_number, group)
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        return LabSession(**{k: data[k] for k in LabSession.__dataclass_fields__ if k in data})

    session = find_lab_session(
        subject=subject,
        lab_number=lab_number,
        group=group,
        schedule_dir=schedule_dir,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(session), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info("Wrote held-on {} → {}", session.date, path)
    return session


def find_lab_session(
    *,
    subject: str,
    lab_number: int,
    group: str,
    schedule_dir: Path | None = None,
) -> LabSession:
    if lab_number < 1:
        raise SystemExit(f"Lab number must be ≥ 1, got {lab_number}")
    sessions = list_group_lab_sessions(
        subject=subject,
        group=group,
        schedule_dir=schedule_dir,
    )
    code = _subject_code(subject)
    if not sessions:
        raise SystemExit(
            f"No «{code} Лб» sessions for group {group!r} in parsed schedule. "
            f"Run: python -m nure_dl schedule-parse"
        )
    if lab_number > len(sessions):
        raise SystemExit(
            f"Lab {lab_number} needs the {lab_number}-th session for {group}, "
            f"but schedule only has {len(sessions)}: "
            + ", ".join(s.date for s in sessions)
        )
    return sessions[lab_number - 1]


def list_group_lab_sessions(
    *,
    subject: str,
    group: str,
    schedule_dir: Path | None = None,
) -> list[LabSession]:
    """Chronological unique-date Лб sessions for subject+group from parsed.json."""
    parsed = load_parsed_schedule(schedule_dir)
    code = _subject_code(subject)
    matched: list[LabSession] = []
    seen_dates: set[str] = set()
    for entry in parsed.entries:
        if entry.subject != code or entry.kind != "Лб":
            continue
        if not _group_matches(entry.groups, group):
            continue
        if entry.date in seen_dates:
            continue
        seen_dates.add(entry.date)
        matched.append(
            LabSession(
                date=entry.date,
                weekday=entry.weekday,
                time=entry.time,
                group=_pick_group_label(entry.groups, group),
                subject=code,
                cell=entry.raw,
                source=parsed.source,
                week=entry.week,
                pair=entry.pair,
            )
        )
    return matched


def lab_number_from_title(lab_title: str) -> int | None:
    match = re.search(
        r"(?:лабораторн\w*\s+робот\w*|лр|лб)\s*№?\s*(\d+)",
        lab_title,
        re.I,
    )
    if match:
        return int(match.group(1))
    match = re.search(r"\b(\d+)\b", lab_title)
    return int(match.group(1)) if match else None


def _parse_grid(table) -> list[ScheduleEntry]:
    entries: list[ScheduleEntry] = []
    current_dates: list[date | None] = []
    current_day = ""
    for tr in table.select("tr"):
        texts = [c.get_text(" ", strip=True) for c in tr.select("th, td")]
        if not texts:
            continue
        first = texts[0]
        if first in _DAY_NAMES:
            current_day = first
            current_dates = _parse_week_dates(texts[1:])
            continue
        if first == "№" or first == "Тижні" or not first.isdigit():
            continue
        if not current_dates:
            continue
        pair = int(first)
        time = texts[1] if len(texts) > 1 else ""
        week_cells = texts[2:] if len(texts) > 2 else []
        for i, cell in enumerate(week_cells):
            if not cell or i >= len(current_dates) or current_dates[i] is None:
                continue
            parsed_cell = _parse_cell(cell)
            if parsed_cell is None:
                continue
            subject, kind, mode, groups = parsed_cell
            entries.append(
                ScheduleEntry(
                    date=current_dates[i].isoformat(),  # type: ignore[union-attr]
                    weekday=current_day,
                    week=i + 1,
                    pair=pair,
                    time=time,
                    subject=subject,
                    kind=kind,
                    mode=mode,
                    groups=groups,
                    raw=cell,
                )
            )
    entries.sort(key=lambda e: (e.date, e.pair, e.time))
    return entries


def _parse_cell(cell: str) -> tuple[str, str, str, list[str]] | None:
    match = _CELL_RE.match(cell.strip())
    if not match:
        return None
    groups = [g.strip() for g in re.split(r"[;,]", match.group("groups")) if g.strip()]
    if not groups:
        return None
    return (
        match.group("subject"),
        match.group("kind"),
        match.group("mode"),
        groups,
    )


def _parse_teacher(soup: BeautifulSoup) -> str:
    text = soup.get_text("\n", strip=True)
    match = re.search(r"Розклад на викладача\(ів\):\s*(.+)", text)
    if match:
        return match.group(1).strip()
    # broken encoding fallback label from title
    if soup.title:
        return soup.title.get_text(strip=True)
    return ""


def _parse_legend(soup: BeautifulSoup) -> dict[str, str]:
    subjects: dict[str, str] = {}
    for table in soup.select("table"):
        rows = table.select("tr")
        if len(rows) < 1:
            continue
        for tr in rows:
            cells = [c.get_text(" ", strip=True) for c in tr.select("td, th")]
            if len(cells) >= 2 and re.fullmatch(r"[A-ZА-ЯІЇЄҐ]{2,8}", cells[0]):
                subjects[cells[0]] = cells[1]
    return subjects


def _find_html(root: Path) -> Path:
    files = sorted(root.glob("*.html"))
    if not files:
        raise SystemExit(
            f"No schedule HTML in {root.resolve()}. "
            "Save the teacher schedule under local/schedule/."
        )
    return files[0]


def _read_html(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "cp1251", "windows-1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("cp1251", errors="replace")


def _parse_week_dates(cells: list[str]) -> list[date | None]:
    out: list[date | None] = []
    for text in cells:
        match = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", text.strip())
        if not match:
            out.append(None)
            continue
        out.append(
            date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        )
    return out


def _subject_code(subject: str) -> str:
    key = subject.strip()
    if key in SUBJECT_SLUGS:
        return SUBJECT_SLUGS[key]
    lower = key.casefold()
    if lower in SUBJECT_SLUGS:
        return SUBJECT_SLUGS[lower]
    # already a schedule code
    return key.upper() if key.isascii() else key


def _subject_slug(subject: str) -> str:
    code = _subject_code(subject)
    for slug, c in SUBJECT_SLUGS.items():
        if c == code and slug.isascii():
            return slug
    return re.sub(r"[^\w\-]+", "-", code.casefold()).strip("-") or "subject"


def _group_matches(groups: list[str], requested: str) -> bool:
    needle = _norm_group(requested)
    tail = _group_tail(requested)
    for g in groups:
        ng = _norm_group(g)
        if ng == needle or needle in ng or ng in needle:
            return True
        if tail and _group_tail(g) == tail:
            return True
    return False


def _norm_group(group: str) -> str:
    return re.sub(r"\s+", "", group).casefold().replace("і", "и").replace("ї", "и")


def _group_tail(group: str) -> str:
    match = re.search(r"(\d{2}-\d+)\s*$", group.strip())
    return match.group(1) if match else ""


def _group_slug(group: str) -> str:
    slug = re.sub(r"[^\w\-]+", "-", group.strip(), flags=re.UNICODE)
    return slug.strip("-") or "group"


def _pick_group_label(groups: list[str], requested: str) -> str:
    tail = _group_tail(requested)
    for g in groups:
        if tail and _group_tail(g) == tail:
            return g
    return groups[0] if groups else requested
