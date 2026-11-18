from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from bs4 import BeautifulSoup

from nure_dl.client import MoodleClient
from nure_dl.models import LabAssignment

# Themes use "Лабораторні роботи КІУКІ-23-1" or "Лабораторні роботи: КІУКІ-24-1"
_LAB_SECTION_RE = re.compile(r"^Лабораторні роботи[:\s]+(.+)$")
_ASSIGN_NAME_RE = re.compile(r"\s+Assignment$", re.IGNORECASE)
# Moodle assign titles: "{shortname}: {activity} | Site"
_ASSIGN_PAGE_TITLE_RE = re.compile(
    r"^(?P<shortname>.+?):\s+(?P<activity>.+?)(?:\s*\|\s*.+)?$"
)


def discover_labs(
    client: MoodleClient, course_id: int
) -> tuple[list[LabAssignment], str | None, str | None]:
    """Return labs and the full and short course names used for matching."""
    html = client.get_text(f"/course/view.php?id={course_id}")
    fullname = parse_course_fullname(html)
    labs = labs_from_course_sections(
        client.get_course_sections(course_id, html), course_id
    ) or parse_lab_assignments(html, client.base_url, course_id, "")
    shortname = None
    if labs:
        assign_html = client.get_text(f"/mod/assign/view.php?id={labs[0].assign_id}")
        shortname = parse_course_shortname_from_assign(assign_html)
    course_name = resolve_course_name(fullname, shortname, course_id)
    return [replace(lab, course_name=course_name) for lab in labs], fullname, shortname


def parse_course_fullname(course_html: str) -> str | None:
    soup = BeautifulSoup(course_html, "lxml")
    for selector in (
        ".page-header-headings h1",
        "#page-header h1",
        "h1",
    ):
        el = soup.select_one(selector)
        if el is not None:
            text = " ".join(el.stripped_strings)
            if text:
                return text
    if soup.title:
        title = soup.title.get_text(strip=True)
        title = re.sub(r"^Course:\s*", "", title, flags=re.IGNORECASE)
        title = re.split(r"\s*\|\s*", title, maxsplit=1)[0].strip()
        return title or None
    return None


def parse_course_shortname_from_assign(assign_html: str) -> str | None:
    soup = BeautifulSoup(assign_html, "lxml")
    if not soup.title:
        return None
    raw = soup.title.get_text(strip=True)
    match = _ASSIGN_PAGE_TITLE_RE.match(raw)
    if not match:
        return None
    return match.group("shortname").strip() or None


def resolve_course_name(
    fullname: str | None,
    shortname: str | None,
    course_id: int,
) -> str:
    """Prefer Moodle shortname (distinguishes streams); else fullname; else id."""
    if shortname:
        return shortname
    if fullname:
        return fullname
    return str(course_id)


def parse_lab_assignments(
    course_html: str,
    base_url: str,
    course_id: int,
    course_name: str,
) -> list[LabAssignment]:
    """Parse course page into lab assignments under group lab sections."""
    soup = BeautifulSoup(course_html, "lxml")
    labs: list[LabAssignment] = []

    for section in soup.select("li.section, div.section"):
        name_el = section.select_one(".sectionname")
        if name_el is None:
            continue
        section_title = " ".join(name_el.stripped_strings)
        match = _LAB_SECTION_RE.match(section_title)
        if not match:
            continue
        group = match.group(1).strip()
        for link in section.select('a[href*="/mod/assign/view.php"]'):
            href = link.get("href", "")
            id_match = re.search(r"[?&]id=(\d+)", href)
            if not id_match:
                continue
            inst = link.select_one(".instancename")
            title = (
                " ".join(inst.stripped_strings)
                if inst is not None
                else link.get_text(" ", strip=True)
            )
            title = _ASSIGN_NAME_RE.sub("", title).strip()
            labs.append(
                LabAssignment(
                    course_id=course_id,
                    course_name=course_name,
                    group=group,
                    assign_id=id_match.group(1),
                    title=title,
                )
            )

    if labs:
        return _dedupe(labs)
    return _parse_lab_assignments_linear(course_html, base_url, course_id, course_name)


def labs_from_course_sections(
    sections: list[dict[str, Any]], course_id: int
) -> list[LabAssignment]:
    labs: list[LabAssignment] = []
    for section in sections:
        title = section.get("title") or section.get("name") or ""
        match = _LAB_SECTION_RE.match(" ".join(title.split()))
        if match is None:
            continue
        for module in section.get("modules", []):
            if (module.get("module") or module.get("modname")) != "assign":
                continue
            labs.append(
                LabAssignment(
                    course_id=course_id,
                    course_name="",
                    group=match[1].strip(),
                    assign_id=str(module["id"]),
                    title=_ASSIGN_NAME_RE.sub("", module["name"]).strip(),
                )
            )
    return _dedupe(labs)


def _dedupe(labs: list[LabAssignment]) -> list[LabAssignment]:
    seen: set[str] = set()
    out: list[LabAssignment] = []
    for lab in labs:
        if lab.assign_id in seen:
            continue
        seen.add(lab.assign_id)
        out.append(lab)
    return out


def _parse_lab_assignments_linear(
    course_html: str,
    base_url: str,
    course_id: int,
    course_name: str,
) -> list[LabAssignment]:
    pattern = re.compile(
        r'class="[^"]*sectionname[^"]*"[^>]*>(.*?)</(?:span|a|h3|h4)>'
        r'|href="(?:'
        + re.escape(base_url)
        + r')?/mod/assign/view\.php\?id=(\d+)"[^>]*>\s*'
        r'<span class="instancename">(.*?)</span>',
        re.IGNORECASE | re.DOTALL,
    )
    labs: list[LabAssignment] = []
    current_group: str | None = None
    for match in pattern.finditer(course_html):
        if match.group(1) is not None and match.group(2) is None:
            title = re.sub(r"<[^>]+>", "", match.group(1))
            title = re.sub(r"\s+", " ", title).strip()
            sec = _LAB_SECTION_RE.match(title)
            current_group = sec.group(1).strip() if sec else None
            continue
        if match.group(2) and current_group:
            title = re.sub(r"<[^>]+>", "", match.group(3))
            title = _ASSIGN_NAME_RE.sub("", title).strip()
            labs.append(
                LabAssignment(
                    course_id=course_id,
                    course_name=course_name,
                    group=current_group,
                    assign_id=match.group(2),
                    title=title,
                )
            )
    return _dedupe(labs)
