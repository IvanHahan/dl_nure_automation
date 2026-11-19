"""Prepare and create Moodle activities for labs in the teacher timetable."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from bs4 import BeautifulSoup, Tag

from nure_dl.client import MoodleClient
from nure_dl.course import _LAB_SECTION_RE, parse_course_fullname
from nure_dl.schedule import (
    ParsedSchedule,
    ScheduledLab,
    lab_number_from_title,
    scheduled_labs,
)


@dataclass(frozen=True)
class LabActivities:
    lab: ScheduledLab
    group: str
    name: str
    course_id: int
    section_number: int
    attendance_id: str
    assignment_exists: bool
    attendance_exists: bool


def plan_activities(
    client: MoodleClient,
    course_ids: tuple[int, ...],
    schedule: ParsedSchedule,
    day: date,
) -> list[LabActivities]:
    labs = scheduled_labs(schedule, day)
    if not labs:
        return []

    courses = {}
    for course_id in course_ids:
        html = client.get_text(f"/course/view.php?id={course_id}")
        sections = client.get_course_sections(course_id, html)
        if not sections:
            raise SystemExit(
                f"Could not verify Moodle sections for course {course_id}."
            )
        courses[course_id] = (parse_course_fullname(html) or "", sections)

    plan = []
    seen_groups = set()
    for lab in labs:
        if lab.last_pair != lab.first_pair + 1:
            raise SystemExit(
                f"Expected two consecutive slots for {lab.subject} {', '.join(lab.groups)}."
            )
        if len(lab.groups) != 1 or (lab.subject, lab.groups[0]) in seen_groups:
            raise SystemExit(
                "Activity creation needs one scheduled lab per group per day."
            )
        group = lab.groups[0]
        seen_groups.add((lab.subject, group))
        number = len(
            {
                entry.date
                for entry in schedule.entries
                if entry.kind == "Лб"
                and entry.subject == lab.subject
                and group in entry.groups
                and entry.date <= lab.date
            }
        )
        name = f"Лабораторна робота {number}"
        targets = []
        for course_id, (course_name, sections) in courses.items():
            if not _matches_subject(course_name, lab.subject, schedule.subjects):
                continue
            for section in sections:
                match = _LAB_SECTION_RE.fullmatch(
                    section.get("title") or section.get("name") or ""
                )
                if match and match[1].strip().casefold() == group.casefold():
                    targets.append((course_id, section))
        if len(targets) != 1:
            raise SystemExit(
                f"Expected one Moodle lab section for {lab.subject} {group}, found {len(targets)}."
            )
        course_id, section = targets[0]
        attendance = [
            module
            for course_section in courses[course_id][1]
            for module in course_section["modules"]
            if module.get("module") == "attendance"
        ]
        if len(attendance) != 1:
            raise SystemExit(
                f"Expected one Attendance activity for course {course_id}."
            )
        attendance_id = str(attendance[0]["id"])
        plan.append(
            LabActivities(
                lab,
                group,
                name,
                course_id,
                int(section["number"]),
                attendance_id,
                _assignment_exists(section, name),
                _attendance_exists(client, attendance_id, lab, group, name),
            )
        )
    return plan


def _matches_subject(course_name: str, subject: str, subjects: dict[str, str]) -> bool:
    def words(name: str) -> str:
        normalized = name.casefold().translate(str.maketrans("єї", "еі", "'’`ʼ"))
        return " ".join(re.findall(r"\w+", normalized))

    course = words(course_name)
    if course == words(subject):
        return True
    scheduled = words(subjects.get(subject, ""))
    # NURE headings can be truncated in the middle of a word.
    return bool(len(course.split()) >= 3 and scheduled.startswith(course))


def _assignment_exists(section: dict, name: str) -> bool:
    return any(
        module.get("module") == "assign"
        and re.match(r"^(?:лабораторн|лр|лб)", title, re.IGNORECASE)
        and lab_number_from_title(title) == lab_number_from_title(name)
        for module in section["modules"]
        if (title := (module.get("name") or "").strip())
    )


def _attendance_exists(
    client: MoodleClient, attendance_id: str, lab: ScheduledLab, group: str, name: str
) -> bool:
    html = client.get_text(
        f"/mod/attendance/manage.php?id={attendance_id}&view=5&lang=en"
    )
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.generaltable")
    if table is None and not soup.select_one(
        'a[href*="sessions.php"][href*="action=1"]'
    ):
        raise SystemExit(f"Could not verify Attendance activity {attendance_id}.")
    if table is None:
        return False
    day_label = date.fromisoformat(lab.date).strftime("%a %d %b %Y").replace(" 0", " ")
    for row in table.select("tbody tr"):
        cells = row.select("td.cell")
        if len(cells) < 5:
            continue
        session_day, hours, audience, description = (
            cell.get_text(" ", strip=True) for cell in cells[1:5]
        )
        if session_day.replace("Sept", "Sep").replace(" 0", " ") != day_label:
            continue
        if audience != f"Group: {group}":
            continue
        try:
            window = tuple(
                datetime.strptime(
                    value.strip().replace(" ", ""),
                    "%I:%M%p" if ":" in value else "%I%p",
                ).strftime("%H:%M")
                for value in hours.split("-")
            )
        except ValueError:
            window = ()
        same_window = window == (lab.starts_at, lab.ends_at)
        if description == name and same_window:
            return True
        if description == name or same_window:
            raise SystemExit(
                f"{group} has a conflicting attendance session: {description} at {hours}."
            )
    return False


def _load_form(
    client: MoodleClient, path: str, marker: str
) -> tuple[Tag, dict[str, str | int]]:
    soup = BeautifulSoup(client.get_text(path), "lxml")
    form = soup.select_one(f'form.mform:has(input[name="{marker}"])')
    if form is None:
        raise SystemExit(f"Moodle did not return the expected form at {path}.")
    data: dict[str, str | int] = {}
    for field in form.select("input[name], select[name], textarea[name]"):
        name = field["name"]
        kind = field.get("type")
        if field.has_attr("disabled") or kind in {"submit", "button", "reset", "file"}:
            continue
        if kind in {"checkbox", "radio"} and not field.has_attr("checked"):
            continue
        if field.name == "select":
            option = field.select_one("option[selected]")
            if option is None and not field.has_attr("multiple"):
                option = field.select_one("option")
            if option is not None:
                data[name] = option.get("value", "")
        elif field.name == "textarea":
            data[name] = field.get_text()
        else:
            data[name] = field.get("value", "")
    return form, data


def apply_activities(client: MoodleClient, plan: list[LabActivities]) -> None:
    for target in plan:
        if not target.attendance_exists:
            _create_attendance(client, target)
        if not target.assignment_exists:
            _create_assignment(client, target)


def _create_attendance(client: MoodleClient, target: LabActivities) -> None:
    path = f"/mod/attendance/sessions.php?id={target.attendance_id}&action=1"
    form, data = _load_form(client, path, "_qf__mod_attendance_form_addsession")
    groups = [
        option["value"]
        for option in form.select('select[name="groups[]"] option[value]')
        if option.get_text(" ", strip=True) == target.group
    ]
    if len(groups) != 1:
        raise SystemExit(f"Could not uniquely match Attendance group {target.group}.")
    day = date.fromisoformat(target.lab.date)
    start = target.lab.starts_at.split(":")
    end = target.lab.ends_at.split(":")
    data.update(
        {
            "sessiontype": 1,
            "groups[]": groups[0],
            "sessiondate[day]": day.day,
            "sessiondate[month]": day.month,
            "sessiondate[year]": day.year,
            "sestime[starthour]": int(start[0]),
            "sestime[startminute]": int(start[1]),
            "sestime[endhour]": int(end[0]),
            "sestime[endminute]": int(end[1]),
            "sdescription[text]": target.name,
            "submitbutton": "Add",
        }
    )
    data.pop("addmultiply", None)
    client.post_form(
        "/mod/attendance/sessions.php", data, referer=client.base_url + path
    )
    if not _attendance_exists(
        client, target.attendance_id, target.lab, target.group, target.name
    ):
        raise SystemExit(
            f"Moodle did not confirm attendance creation for {target.group}."
        )


def _create_assignment(client: MoodleClient, target: LabActivities) -> None:
    path = (
        f"/course/modedit.php?add=assign&course={target.course_id}"
        f"&section={target.section_number}&return=0&sr=0"
    )
    _, data = _load_form(client, path, "_qf__mod_assign_mod_form")
    day = date.fromisoformat(target.lab.date)
    hour, minute = map(int, target.lab.starts_at.split(":"))
    data.update(
        {
            "name": target.name,
            "grade[modgrade_point]": 100,
            "assignsubmission_file_enabled": 1,
            "allowsubmissionsfromdate[enabled]": 1,
            "allowsubmissionsfromdate[day]": day.day,
            "allowsubmissionsfromdate[month]": day.month,
            "allowsubmissionsfromdate[year]": day.year,
            "allowsubmissionsfromdate[hour]": hour,
            "allowsubmissionsfromdate[minute]": minute,
            "submitbutton2": "Save and return to course",
        }
    )
    for field in ("duedate", "cutoffdate", "gradingduedate"):
        data.pop(f"{field}[enabled]", None)
    client.post_form("/course/modedit.php", data, referer=client.base_url + path)
    html = client.get_text(f"/course/view.php?id={target.course_id}")
    sections = client.get_course_sections(target.course_id, html)
    if not any(
        int(section["number"]) == target.section_number
        and _assignment_exists(section, target.name)
        for section in sections
    ):
        raise SystemExit(
            f"Moodle did not confirm assignment creation for {target.group}."
        )
