from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LabAssignment:
    course_id: int
    course_name: str
    group: str
    assign_id: str
    title: str


@dataclass(frozen=True)
class SubmissionFile:
    student_name: str
    student_email: str
    filename: str
    url: str
