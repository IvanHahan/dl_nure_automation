from __future__ import annotations

import re
from functools import partial
from pathlib import Path
from typing import Any, Self

import httpx
import requests
from loguru import logger
from py_moodle.course import MoodleCourseError, get_course
from py_moodle.transport import TransportError
from py_moodle.transport.ajax import call as call_ajax

_SESSKEY_RE = re.compile(r'"sesskey"\s*:\s*"([^"]+)"')
_ASSIGNMENT_INSTANCE_RE = re.compile(r'\bdata-assignmentid="([0-9]+)"')


class MoodleClient:
    def __init__(self, base_url: str, session: str, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout
        # Cookie jar (not a static Cookie header) so Moodle can rotate MoodleSession
        # after POSTs (e.g. save grade) without kicking us to login.
        self._client = httpx.Client(
            base_url=self.base_url,
            cookies={"MoodleSession": session},
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            },
            follow_redirects=True,
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get_text(self, path_or_url: str) -> str:
        response = self._client.get(path_or_url)
        response.raise_for_status()
        if "/login/index.php" in str(response.url):
            raise SystemExit(
                "Redirected to login — MoodleSession expired. Refresh .env from DevTools."
            )
        return response.text

    def get_course_sections(
        self, course_id: int, course_html: str
    ) -> list[dict[str, Any]]:
        sesskey = _SESSKEY_RE.search(course_html)
        if sesskey is None:
            return []

        with self._requests_session() as session:
            try:
                return get_course(session, self.base_url, sesskey[1], course_id)
            except (MoodleCourseError, requests.RequestException, ValueError):
                logger.debug("Course API unavailable for course {}", course_id)
                return []

    def get_assignment_participants(self, module_id: str) -> list[dict[str, Any]]:
        try:
            html = self.get_text(f"/mod/assign/view.php?id={module_id}&action=grader")
            sesskey = _SESSKEY_RE.search(html)
            assignment = _ASSIGNMENT_INSTANCE_RE.search(html)
            if sesskey is None or assignment is None:
                return []
            with self._requests_session() as session:
                participants = call_ajax(
                    session,
                    self.base_url,
                    "mod_assign_list_participants",
                    sesskey[1],
                    {
                        "assignid": int(assignment[1]),
                        "groupid": 0,
                        "filter": "",
                        "includeenrolments": False,
                    },
                )
        except (httpx.HTTPError, TransportError, requests.RequestException):
            logger.debug("Participant API unavailable for module {}", module_id)
            return []
        if not isinstance(participants, list) or not all(
            isinstance(row, dict) for row in participants
        ):
            return []
        return participants

    def _requests_session(self) -> requests.Session:
        session = requests.Session()
        session.cookies = self._client.cookies.jar
        session.request = partial(session.request, timeout=self._timeout)
        return session

    def post_form(
        self,
        path_or_url: str,
        data: dict[str, str | int],
        *,
        referer: str | None = None,
        allow_login_redirect: bool = False,
    ) -> httpx.Response:
        headers: dict[str, str] = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if referer:
            headers["Referer"] = referer
            headers["Origin"] = self.base_url
        response = self._client.post(path_or_url, data=data, headers=headers)
        response.raise_for_status()
        if "/login/index.php" in str(response.url) and not allow_login_redirect:
            raise SystemExit(
                "Redirected to login — MoodleSession expired. Refresh .env from DevTools."
            )
        return response

    def download(self, url: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._client.stream("GET", url) as response:
            response.raise_for_status()
            if "/login/index.php" in str(response.url):
                raise SystemExit("Session expired while downloading a file.")
            tmp = dest.with_suffix(dest.suffix + ".partial")
            with tmp.open("wb") as fh:
                for chunk in response.iter_bytes():
                    fh.write(chunk)
            tmp.replace(dest)
        logger.debug("Saved {}", dest)
