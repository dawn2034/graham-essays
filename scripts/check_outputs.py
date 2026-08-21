#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

EXPECTED_TITLE = "Paul Graham: Selected Essays"
EXPECTED_AUTHOR = "Paul Graham"
PAGE_SIZES_PT = {
    "A5": (419.53, 595.28),
    "B5": (498.90, 708.66),
    "A4": (595.28, 841.89),
}
PAGE_TOLERANCE_PT = 0.8


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.translate(
        str.maketrans(
            {
                "’": "'",
                "‘": "'",
                "“": '"',
                "”": '"',
                "\u00a0": " ",
            }
        )
    )
    return " ".join(value.split()).strip().casefold()


def canonical_title(value: str) -> str:
    """Normalize a title and ignore an optional generated article number."""
    return re.sub(r"^\d{1,4}\s+", "", normalize(value))


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def run(*args: str) -> str:
    completed = subprocess.run(args, check=True, text=True, capture_output=True)
    return completed.stdout


def fail(message: str) -> None:
    raise RuntimeError(message)


def parse_pdfinfo(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def epub_toc_titles(archive: zipfile.ZipFile) -> list[str]:
    nav_names = [
        name
        for name in archive.namelist()
        if name.lower().endswith("nav.xhtml")
    ]
    if not nav_names:
        fail("EPUB 3 navigation document is missing")

    root = ET.fromstring(archive.read(nav_names[0]))
    toc_nav = None
    for element in root.iter():
        if local_name(element.tag) != "nav":
            continue
        epub_type = next(
            (
                value
                for key, value in element.attrib.items()
                if local_name(key) == "type"
            ),
            "",
        )
        if "toc" in epub_type.split():
            toc_nav = element
            break
    if toc_nav is None:
        fail("EPUB navigation document has no table-of-contents nav")

    titles: list[str] = []
    for element in toc_nav.iter():
        if local_name(element.tag) == "a":
            text = " ".join("".join(element.itertext()).split())
            if text:
                titles.append(text)
    return titles


def epub_metadata(archive: zipfile.ZipFile) -> tuple[list[str], list[str], list[str]]:
    opf_names = [name for name in archive.namelist() if name.lower().endswith(".opf")]
    if len(opf_names) != 1:
        fail(f"Expected one EPUB package document, found {len(opf_names)}")
    root = ET.fromstring(archive.read(opf_names[0]))

    titles: list[str] = []
    creators: list[str] = []
    specified_fonts: list[str] = []
    for element in root.iter():
        name = local_name(element.tag)
        text = " ".join((element.text or "").split())
        if name == "title" and text:
            titles.append(text)
        elif name == "creator" and text:
            creators.append(text)
        elif name == "meta" and element.attrib.get("property") == "ibooks:specified-fonts":
            specified_fonts.append(text)
    return titles, creators, specified_fonts


def check_epub(
    path: Path, included_titles: list[str], excluded_titles: list[str]
) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        fail(f"EPUB is missing or empty: {path}")

    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            fail(f"EPUB CRC failure: {bad}")
        names = archive.namelist()
        if not names or names[0] != "mimetype":
            fail("EPUB mimetype must be the first archive entry")
        mimetype_info = archive.getinfo("mimetype")
        if mimetype_info.compress_type != zipfile.ZIP_STORED:
            fail("EPUB mimetype entry must be uncompressed")
        if archive.read("mimetype") != b"application/epub+zip":
            fail("EPUB mimetype is invalid")

        display_path = "META-INF/com.apple.ibooks.display-options.xml"
        if display_path not in names:
            fail("Apple Books display-options patch is missing")
        display_text = archive.read(display_path).decode("utf-8", errors="replace")
        if "specified-fonts" not in display_text or ">false<" not in display_text:
            fail("Apple Books must be allowed to override specified fonts")

        package_titles, creators, specified_fonts = epub_metadata(archive)
        if package_titles != [EXPECTED_TITLE]:
            fail(f"Unexpected EPUB title metadata: {package_titles}")
        if creators != [EXPECTED_AUTHOR]:
            fail(f"Unexpected EPUB creator metadata: {creators}")
        if specified_fonts != ["false"]:
            fail(f"Unexpected ibooks:specified-fonts metadata: {specified_fonts}")

        toc_titles = epub_toc_titles(archive)

    expected = [canonical_title(title) for title in included_titles]
    actual = [canonical_title(title) for title in toc_titles]
    counts = Counter(actual)
    if len(actual) != len(expected):
        fail(
            "EPUB chapter count differs from essays.csv: "
            f"navigation={len(actual)}, csv={len(expected)}"
        )
    missing_or_duplicate = [
        title for title in included_titles if counts[canonical_title(title)] != 1
    ]
    if missing_or_duplicate:
        preview = ", ".join(missing_or_duplicate[:8])
        suffix = " ..." if len(missing_or_duplicate) > 8 else ""
        fail("EPUB chapter titles missing or duplicated: " + preview + suffix)
    leaked = [title for title in excluded_titles if counts[canonical_title(title)] > 0]
    if leaked:
        fail("Excluded chapter titles leaked into EPUB navigation: " + ", ".join(leaked))


def check_pdf(
    path: Path,
    included_titles: list[str],
    excluded_titles: list[str],
    paper_label: str,
) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        fail(f"PDF is missing or empty: {path}")

    info = parse_pdfinfo(run("pdfinfo", str(path)))
    if info.get("Title") != EXPECTED_TITLE:
        fail(f"Unexpected PDF title metadata: {info.get('Title', 'missing')}")
    if info.get("Author") != EXPECTED_AUTHOR:
        fail(f"Unexpected PDF author metadata: {info.get('Author', 'missing')}")
    if info.get("Encrypted", "").lower() != "no":
        fail("PDF must not be encrypted")

    page_size = info.get("Page size", "")
    match = re.search(r"([0-9.]+) x ([0-9.]+) pts", page_size)
    if not match:
        fail(f"Could not parse PDF page size: {page_size or 'missing'}")
    width, height = map(float, match.groups())
    expected_width, expected_height = PAGE_SIZES_PT[paper_label]
    if (
        abs(width - expected_width) > PAGE_TOLERANCE_PT
        or abs(height - expected_height) > PAGE_TOLERANCE_PT
    ):
        fail(f"PDF is not {paper_label}: {page_size}")

    font_lines = [
        line
        for line in run("pdffonts", str(path)).splitlines()[2:]
        if line.strip()
    ]
    if not font_lines:
        fail("PDF contains no detectable fonts")
    for line in font_lines:
        columns = line.split()
        # Parse from the right because a font type may itself contain spaces.
        if len(columns) < 9:
            fail("Could not parse pdffonts output: " + line)
        embedded = columns[-5]
        subset = columns[-4]
        if embedded != "yes" or subset != "yes":
            fail("A PDF font is not embedded and subset: " + line)

    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        fail(f"PyMuPDF is required for PDF outline validation: {exc}")

    with fitz.open(path) as document:
        for index, page in enumerate(document, start=1):
            rect = page.rect
            if (
                abs(rect.width - expected_width) > PAGE_TOLERANCE_PT
                or abs(rect.height - expected_height) > PAGE_TOLERANCE_PT
            ):
                fail(
                    f"PDF page {index} is not {paper_label}: "
                    f"{rect.width:.2f} x {rect.height:.2f} pt"
                )
        raw_outline = document.get_toc(simple=True)
        if any(page < 1 or page > document.page_count for _, _, page in raw_outline):
            fail("PDF outline contains an invalid page destination")

    outline_titles = [canonical_title(item[1]) for item in raw_outline]
    counts = Counter(outline_titles)
    expected = [canonical_title(title) for title in included_titles]
    if len(outline_titles) != len(expected):
        fail(
            "PDF outline chapter count differs from essays.csv: "
            f"outline={len(outline_titles)}, csv={len(expected)}"
        )
    missing_or_duplicate = [
        title for title in included_titles if counts[canonical_title(title)] != 1
    ]
    if missing_or_duplicate:
        preview = ", ".join(missing_or_duplicate[:8])
        suffix = " ..." if len(missing_or_duplicate) > 8 else ""
        fail("PDF outline titles missing or duplicated: " + preview + suffix)
    leaked = [title for title in excluded_titles if counts[canonical_title(title)] > 0]
    if leaked:
        fail("Excluded chapter titles leaked into PDF outline: " + ", ".join(leaked))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epub", type=Path, required=True)
    parser.add_argument("--pdf-a5", type=Path, required=True)
    parser.add_argument("--pdf-b5", type=Path, required=True)
    parser.add_argument("--pdf-a4", type=Path, required=True)
    parser.add_argument("--included", type=Path, required=True)
    parser.add_argument("--excluded", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    configured = [item["title"] for item in manifest["excluded"]]
    expected_excluded = int(
        manifest.get("expected_exclusion_count", len(configured))
    )
    if len(configured) != expected_excluded:
        fail("Selection manifest count is inconsistent")

    with args.included.open(encoding="utf-8", newline="") as handle:
        included_rows = list(csv.DictReader(handle))
    with args.excluded.open(encoding="utf-8", newline="") as handle:
        excluded_rows = list(csv.DictReader(handle))
    if len(excluded_rows) != expected_excluded:
        fail(
            f"Expected {expected_excluded} exclusion audit rows, "
            f"found {len(excluded_rows)}"
        )
    if any(row.get("Status") != "excluded" for row in excluded_rows):
        fail("Every configured exclusion must match the live index")

    included_title_list = [row["Title"] for row in included_rows]
    included_titles = {normalize(title) for title in included_title_list}
    overlap = [title for title in configured if normalize(title) in included_titles]
    if overlap:
        fail("Excluded titles leaked into essays.csv: " + ", ".join(overlap))

    check_epub(args.epub, included_title_list, configured)
    check_pdf(args.pdf_a5, included_title_list, configured, "A5")
    check_pdf(args.pdf_b5, included_title_list, configured, "B5")
    check_pdf(args.pdf_a4, included_title_list, configured, "A4")
    print(
        f"Outputs validated: {len(included_rows)} included, "
        f"{len(excluded_rows)} excluded; EPUB integrity and A5/B5/A4 PDF checks passed."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"validation error: {exc}", file=sys.stderr)
        raise SystemExit(1)
