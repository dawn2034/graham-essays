#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

EPUB = Path("dist/sample/layout-proof.epub")
PDFS = {
    "A5": (Path("dist/sample/layout-proof-a5.pdf"), 419.53, 595.28),
    "B5": (Path("dist/sample/layout-proof-b5.pdf"), 498.90, 708.66),
    "A4": (Path("dist/sample/layout-proof-a4.pdf"), 595.28, 841.89),
}
EXPECTED = {"Reading Rhythm", "Code and Links", "Long-form Page Test"}
TOLERANCE_PT = 0.8


def fail(message: str) -> None:
    raise RuntimeError(message)


def run(*args: str) -> str:
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def check_pdf(label: str, path: Path, width_expected: float, height_expected: float) -> None:
    if not path.is_file():
        fail(f"{label} layout-proof PDF is missing")

    info = run("pdfinfo", str(path))
    if "Title:           Selected Essays - Layout Proof" not in info:
        fail(f"{label} layout-proof PDF title metadata is wrong")
    match = re.search(r"Page size:\s+([0-9.]+) x ([0-9.]+) pts", info)
    if not match:
        fail(f"Could not parse {label} layout-proof PDF page size")
    width, height = map(float, match.groups())
    if (
        abs(width - width_expected) > TOLERANCE_PT
        or abs(height - height_expected) > TOLERANCE_PT
    ):
        fail(f"Layout-proof PDF is not {label}: {width:.2f} x {height:.2f} pt")

    font_lines = [
        line
        for line in run("pdffonts", str(path)).splitlines()[2:]
        if line.strip()
    ]
    if not font_lines:
        fail(f"{label} layout-proof PDF contains no fonts")
    for line in font_lines:
        columns = line.split()
        if len(columns) < 9 or columns[-5:-3] != ["yes", "yes"]:
            fail(f"A {label} layout-proof PDF font is not embedded and subset: {line}")

    extracted = run("pdftotext", str(path), "-")
    if not EXPECTED.issubset(set(extracted.splitlines())):
        fail(f"{label} layout-proof PDF text extraction is incomplete")


def main() -> int:
    if not EPUB.is_file():
        fail("Layout-proof EPUB is missing")

    with zipfile.ZipFile(EPUB) as archive:
        if archive.testzip():
            fail("Layout-proof EPUB has a CRC error")
        if archive.namelist()[0] != "mimetype":
            fail("Layout-proof EPUB mimetype is not first")
        if archive.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
            fail("Layout-proof EPUB mimetype is compressed")
        nav_name = next(
            (name for name in archive.namelist() if name.endswith("nav.xhtml")),
            None,
        )
        if not nav_name:
            fail("Layout-proof EPUB navigation is missing")
        root = ET.fromstring(archive.read(nav_name))
        nav_titles = {
            " ".join("".join(element.itertext()).split())
            for element in root.iter()
            if local_name(element.tag) == "a"
        }
        if not EXPECTED.issubset(nav_titles):
            fail("Layout-proof EPUB navigation is incomplete")
        display = archive.read(
            "META-INF/com.apple.ibooks.display-options.xml"
        ).decode("utf-8", errors="replace")
        if ">false<" not in display:
            fail("Apple Books font override is not enabled")

    for label, (path, width, height) in PDFS.items():
        check_pdf(label, path, width, height)

    print(
        "Layout proof validated: EPUB integrity, A5/B5/A4 PDFs, fonts, "
        "and sample chapters passed."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"layout-proof validation error: {exc}", file=sys.stderr)
        raise SystemExit(1)
