"""Dump a PDF/DOCX to plain text + image files for the agent to Read."""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf
from docx import Document
from loguru import logger

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def dump_report(path: Path, out_dir: Path) -> Path:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    dest = out_dir.expanduser().resolve() / _safe(path.stem)
    dest.mkdir(parents=True, exist_ok=True)
    images = dest / "images"
    images.mkdir(exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        _dump_docx(path, dest, images)
    elif suffix == ".pdf":
        _dump_pdf(path, dest, images)
    else:
        raise ValueError(f"unsupported type: {suffix}")
    logger.info("Dumped {} → {}", path.name, dest)
    return dest


def _safe(value: str) -> str:
    return _UNSAFE.sub("_", value).strip(" .")[:120] or "report"


def _dump_docx(path: Path, dest: Path, images: Path) -> None:
    doc = Document(path)
    chunks: list[str] = [p.text for p in doc.paragraphs]
    # Listings are often pasted into Word tables — include them
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text = cell.text.strip()
                if text:
                    chunks.append(text)
    (dest / "text.txt").write_text("\n".join(chunks), encoding="utf-8")

    n = 0
    for rel in doc.part.rels.values():
        if "image" not in rel.reltype:
            continue
        n += 1
        part = rel.target_part
        ext = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/gif": ".gif",
            "image/webp": ".webp",
        }.get(getattr(part, "content_type", ""), ".bin")
        (images / f"img-{n:02d}{ext}").write_bytes(part.blob)


def _dump_pdf(path: Path, dest: Path, images: Path) -> None:
    pdf = pymupdf.open(path)
    pages: list[str] = []
    n = 0
    for page in pdf:
        pages.append(page.get_text())
        for img in page.get_images(full=True):
            n += 1
            extracted = pdf.extract_image(img[0])
            ext = "." + (extracted.get("ext") or "bin")
            (images / f"img-{n:02d}{ext}").write_bytes(extracted["image"])
    (dest / "text.txt").write_text("\n".join(pages), encoding="utf-8")
