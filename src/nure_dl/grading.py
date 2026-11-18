from __future__ import annotations

from urllib.parse import parse_qs, unquote, urljoin, urlparse

from bs4 import BeautifulSoup

from nure_dl.models import SubmissionFile


def grading_url(base_url: str, assign_id: str, page: int = 0) -> str:
    return (
        f"{base_url.rstrip('/')}/mod/assign/view.php"
        f"?id={assign_id}&action=grading&status=requiregrading&perpage=100&page={page}"
    )


def parse_ungraded_files(html: str, base_url: str) -> list[SubmissionFile]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.generaltable") or soup.select_one("table.flexible")
    if table is None:
        return []

    results: list[SubmissionFile] = []
    for tr in table.select("tr"):
        if not tr.select("td"):
            continue
        name = _student_name(tr)
        email_el = tr.select_one("td.email")
        email = email_el.get_text(" ", strip=True) if email_el else ""
        for anchor in tr.select('a[href*="pluginfile.php"]'):
            href = anchor.get("href", "").replace("&amp;", "&")
            if "assignsubmission_file" not in href and "submission_files" not in href:
                continue
            url = urljoin(base_url.rstrip("/") + "/", href)
            filename = anchor.get_text(strip=True) or _filename_from_url(url)
            if not filename:
                continue
            results.append(
                SubmissionFile(
                    student_name=name or email or "unknown",
                    student_email=email,
                    filename=filename,
                    url=url,
                )
            )
    return results


def has_next_page(html: str) -> bool:
    soup = BeautifulSoup(html, "lxml")
    for anchor in soup.select("div.paging a, ul.pagination a, a"):
        text = anchor.get_text(strip=True).lower()
        href = anchor.get("href", "")
        if text in {"next", "наступна", "»"} and "action=grading" in href:
            return True
        qs = parse_qs(urlparse(href).query)
        if "page" in qs and text.isdigit():
            # presence of higher page links handled by caller incrementing page
            pass
    # Moodle often uses rel-less Next with page=N
    return any(
        a.get_text(strip=True) in {"Next", "Наступна", "»"}
        for a in soup.select("a[href*='action=grading']")
    )


def _student_name(tr) -> str:
    cell = tr.select_one("td.username")
    if cell is None:
        return ""
    initials = cell.select_one(".userinitials")
    if initials is not None:
        for attr in ("title", "aria-label"):
            label = (initials.get(attr) or "").strip()
            if label:
                return label
    for anchor in cell.select('a[href*="/user/view.php"]'):
        # Drop avatar initials span so "ВК" is not glued to the name
        for span in anchor.select(".userinitials"):
            span.extract()
        text = anchor.get_text(" ", strip=True)
        if text:
            return text
    return cell.get_text(" ", strip=True)


def _filename_from_url(url: str) -> str:
    path = unquote(urlparse(url).path)
    return path.rsplit("/", 1)[-1]
