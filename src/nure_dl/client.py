from __future__ import annotations

from pathlib import Path

import httpx
from loguru import logger


class MoodleClient:
    def __init__(self, base_url: str, session: str, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
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

    def __enter__(self) -> MoodleClient:
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
