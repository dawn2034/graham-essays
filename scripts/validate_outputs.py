#!/usr/bin/env python3
"""Validate selection, EPUB structure and print-PDF invariants."""
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / "selection.json"
SUMMARY = ROOT / "edition-summary.json"
INCLUDED_CSV = ROOT / "essays.csv"
EXCLUDED_CSV = ROOT / "excluded_essays.csv"
EPUB = ROOT / "paul-graham-selected-essays.epub"
PDF = ROOT / "paul-graham-selected-essays.pdf"
REPORT = ROOT / "build-validation.json"


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = (
        value.replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .casefold()
    )
    return " ".join(re.sub(r"[^\w]+", " ", value).split())


def read_titles(path: Path, column: str) -> list[str]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [row[column] for row in csv.DictReader(handle)]


def flatten_outline(items) -> list[str]:
    result: list[str] = []
    for item in items:
        if isinstance(item, list):
            result.extend(flatten_outline(item))
        else:
            title = getattr(item, "title", None)
            if title:
                result.append(str(title))
    return result


def validate_epub(included: list[str], excluded: list[str]) -> dict:
    with zipfile.ZipFile(EPUB) as archive:
        infos = archive.infolist()
        assert infos, "EPUB is empty"
        assert infos[0].filename == "mimetype", "mimetype must be first"
        assert infos[0].compress_type == zipfile.ZIP_STORED, "mimetype must be stored"
        assert archive.read("mimetype") == b"application/epub+zip"
        assert archive.testzip() is None, "EPUB contains a corruped ZIP member"
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        rootfile = container.find(".//{*}rootfile")
        assert rootfile is not None
        opf_path = rootfile.attrib["full-path"]
        opf = ET.fromstring(archive.read(opf_path))
        metadata = opf.find(".//{*}metadata")
        assert metadata is not None, "EPUB package metadata missing"
        title_node = metadata.find("{*}title")
        creator_nodes = metadata.findall("{*}creator")
        assert title_node is not None and title_node.text == "Essays"
        assert any((node.text or "").strip() == "Paul Graham" for node in creator_nodes)
        opf_dir = Path(opf_path).parent
        manifest = {
            item.attrib["id"]: item
            for item in opf.findall(".//{*}manifest/{*}item")
        }
        nav_item = next(
            item for item in manifest.values()
            if "nav" in item.attrib.get("properties", "").split()
        )
        nav_path = str(opf_dir / nav_item.attrib["href"])
        nav = BeautifulSoup(archive.read(nav_path), "xml")
        nav_titles = [a.get_text(" ", strip=True) for a in nav.find_all("a")]
        nav_norm = {normalize(title) for title in nav_titles}
        missing = [title for title in included if normalize(title) not in nav_norm]
        leaked = [title for title in excluded if normalize(title) in nav_norm]
        assert not missing, f"EPUB TOC missing titles: {missing[:5]}"
        assert not leaked, f"EPUB TOC contains excluded titles: {leaked}"
        return {
            "zip_entries": len(infos),
            "toc_links": len(nav_titles),
            "title": title_node.text,
            "creator": "Paul Graham",
            "included_titles_verified": len(included),
        }


def validate_pdf(included: list[str], excluded: list[str]) -> dict:
    reader = PdfReader(str(PDF))
    assert reader.pages, "PDF has no pages"
    metadata = reader.metadata or {}
    assert str(metadata.get("/Title", "")).strip() == "Essays"
    assert "Paul Graham" in str(metadata.get("/Author", ""))
    media = reader.pages[0].mediabox
    width = float(media.width)
    height = float(media.height)
    # ISO A5 is 419.53 x 595.28 pt. XeLaTeX rounds slightly by driver.
    assert abs(width - 419.53) < 2.0 and abs(height - 595.28) < 2.0, (
        width,
        height,
    )
    outline_titles = flatten_outline(reader.outline)
    outline_norm = {normalize(title) for title in outline_titles}
    missing = [title for title in included if normalize(title) not in outline_norm]
    leaked = [title for title in excluded if normalize(title) in outline_norm]
    assert not missing, f"PDF bookmarks missing titles: {missing[:5]}"
    assert not leaked, f"PDF bookmarks contain excluded titles: {leaked}"

    fonts = subprocess.run(
        ["pdffonts", str(PDF)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    font_rows = [line.split() for line in fonts[2:] if line.strip()]
    unsafe_fonts = [
        row
        for row in font_rows
        if len(row) >= 6
        and (row[3].lower() != "yes" or row[4].lower() != "yes")
    ]
    assert not unsafe_fonts, f"PDF fonts are not embedded/subset: {unsafe_fonts}"
    return {
        "pages": len(reader.pages),
        "page_size_points": [round(width, 2), round(height, 2)],
        "bookmark_count": len(outline_titles),
        "included_titles_verified": len(included),
        "title": str(metadata.get("/Title", "")),
        "author": str(metadata.get("/Author", "")),
        "font_programs": len(font_rows),
        "fonts_embedded_and_subset": True,
    }


def main() -> int:
    required = [SELECTION, SUMMARY, INCLUDED_CSV, EXCLUDED_CSV, EPUB, PDF]
    for path in required:
        assert path.is_file(), f"missing required output: {path.name}"

    selection = json.loads(SELECTION.read_text(encoding="utf-8"))
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    configured = [
        title for group in selection["groups"].values() for title in group
    ]
    included = read_titles(INCLUDED_CSV, "Title")
    excluded = read_titles(EXCLUDED_CSV, "Title")

    assert len(configured) == selection["expected_exclusion_count"]
    assert len(excluded) == selection["expected_exclusion_count"]
    assert {normalize(x) for x in configured} == {normalize(x) for x in excluded}
    assert len(included) == summary["included_count"] == summary["downloaded_count"]
    assert len(included) + len(excluded) == summary["source_count"]
    assert summary["source_count"] >= selection["minimum_source_count"]
    assert not summary["failures"]
    assert not ({normalize(x) for x in included} & {normalize(x) for x in excluded})

    report = {
        "selection": {
            "source_count": summary["source_count"],
            "included_count": len(included),
            "excluded_count": len(excluded),
            "configured_exclusions_verified": True,
        },
        "epub": validate_epub(included, excluded),
        "pdf": validate_pdf(included, excluded),
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        raise
