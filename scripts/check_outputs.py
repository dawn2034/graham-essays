#!/usr/bin/env python3
"""Validate EPUB and PDF deliverables beyond mere file existence."""

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
from pathlib import Path

A5_WIDTH_PT = 419.53
A5_HEIGHT_PT = 595.28
PAGE_TOLERANCE_PT = 1.5
EPUB_NS = "http://www.idpf.org/2007/ops"
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
DC_NS = "http://purl.org/dc/elements/1.1/"


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.translate(str.maketrans({"’": "'", "‘": "'", "\u00a0": " "}))
    value = re.sub(r"^\d{3}\s+", "", value.strip())
    return " ".join(value.split()).casefold()


def run(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"{completed.stdout}"
        )
    return completed.stdout


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_csv_titles(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [row["Title"].strip() for row in rows]


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def find_epub_toc_titles(
    zf: zipfile.ZipFile, opf_root: ET.Element, opf_path: str
) -> list[str]:
    opf_ns_match = re.match(r"\{([^}]+)\}", opf_root.tag)
    opf_ns = opf_ns_match.group(1) if opf_ns_match else ""
    ns = {"opf": opf_ns} if opf_ns else {}
    item_path = ".//opf:item" if opf_ns else ".//item"

    nav_href: str | None = None
    for item in opf_root.findall(item_path, ns):
        properties = (item.attrib.get("properties") or "").split()
        if "nav" in properties:
            nav_href = item.attrib.get("href")
            break
    require(bool(nav_href), "EPUB manifest has no navigation document")

    nav_path = str((Path(opf_path).parent / str(nav_href)).as_posix())
    nav_root = ET.fromstring(zf.read(nav_path))

    toc_nav: ET.Element | None = None
    for element in nav_root.iter():
        if local_name(element.tag) != "nav":
            continue
        nav_type = element.attrib.get(f"{{{EPUB_NS}}}type") or element.attrib.get(
            "type"
        )
        if nav_type == "toc":
            toc_nav = element
            break
    require(toc_nav is not None, "EPUB navigation document has no toc nav")

    top_ol = next(
        (child for child in list(toc_nav) if local_name(child.tag) == "ol"), None
    )
    require(top_ol is not None, "EPUB toc has no top-level ordered list")

    titles: list[str] = []
    for li in [child for child in list(top_ol) if local_name(child.tag) == "li"]:
        link = next(
            (element for element in li.iter() if local_name(element.tag) == "a"),
            None,
        )
        if link is not None:
            title = " ".join("".join(link.itertext()).split())
            if title:
                titles.append(title)
    return titles


def check_epub(
    epub_path: Path,
    expected_title: str,
    expected_author: str,
    expected_chapters: int,
    expected_toc_titles: list[str] | None,
) -> dict[str, object]:
    require(epub_path.is_file(), f"EPUB not found: {epub_path}")

    with zipfile.ZipFile(epub_path) as zf:
        bad_entry = zf.testzip()
        require(bad_entry is None, f"corrupt EPUB ZIP member: {bad_entry}")
        infos = zf.infolist()
        require(bool(infos), "EPUB ZIP is empty")
        require(
            infos[0].filename == "mimetype",
            "EPUB mimetype is not the first ZIP entry",
        )
        require(
            infos[0].compress_type == zipfile.ZIP_STORED,
            "EPUB mimetype is compressed",
        )
        require(
            zf.read("mimetype") == b"application/epub+zip",
            "invalid EPUB mimetype",
        )

        display_options = "META-INF/com.apple.ibooks.display-options.xml"
        require(
            display_options in zf.namelist(),
            "Apple Books display options are missing",
        )
        display_text = zf.read(display_options).decode("utf-8", errors="replace")
        require(
            "specified-fonts" in display_text and ">false<" in display_text,
            "Apple Books specified-fonts override is not false",
        )

        container_root = ET.fromstring(zf.read("META-INF/container.xml"))
        rootfile = container_root.find(f".//{{{CONTAINER_NS}}}rootfile")
        require(rootfile is not None, "EPUB container.xml has no rootfile")
        opf_path = rootfile.attrib.get("full-path")
        require(bool(opf_path), "EPUB rootfile has no full-path")

        opf_root = ET.fromstring(zf.read(str(opf_path)))
        titles = [
            " ".join((element.text or "").split())
            for element in opf_root.findall(f".//{{{DC_NS}}}title")
            if (element.text or "").strip()
        ]
        creators = [
            " ".join((element.text or "").split())
            for element in opf_root.findall(f".//{{{DC_NS}}}creator")
            if (element.text or "").strip()
        ]
        require(expected_title in titles, f"EPUB title mismatch: {titles}")
        require(creators == [expected_author], f"EPUB creator mismatch: {creators}")

        toc_titles = find_epub_toc_titles(zf, opf_root, str(opf_path))
        require(
            len(toc_titles) == expected_chapters,
            "EPUB toc count mismatch: "
            f"expected={expected_chapters}, actual={len(toc_titles)}",
        )
        if expected_toc_titles is not None:
            actual_norm = [normalize(title) for title in toc_titles]
            expected_norm = [normalize(title) for title in expected_toc_titles]
            require(
                actual_norm == expected_norm,
                "EPUB toc titles/order do not match essays.csv",
            )

    return {
        "path": str(epub_path),
        "chapters": expected_chapters,
        "title": expected_title,
        "author": expected_author,
    }


def parse_pdfinfo(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            parsed[key.strip()] = value.strip()
    return parsed


def check_pdf(
    pdf_path: Path,
    expected_title: str,
    expected_author: str,
    report_dir: Path,
) -> dict[str, object]:
    require(pdf_path.is_file(), f"PDF not found: {pdf_path}")
    report_dir.mkdir(parents=True, exist_ok=True)

    info_text = run(["pdfinfo", str(pdf_path)])
    fonts_text = run(["pdffonts", str(pdf_path)])
    extracted_text = run(["pdftotext", str(pdf_path), "-"])
    (report_dir / "pdfinfo.txt").write_text(info_text, encoding="utf-8")
    (report_dir / "pdffonts.txt").write_text(fonts_text, encoding="utf-8")

    info = parse_pdfinfo(info_text)
    require(
        info.get("Title") == expected_title,
        f"PDF title mismatch: {info.get('Title')!r}",
    )
    require(
        info.get("Author") == expected_author,
        f"PDF author mismatch: {info.get('Author')!r}",
    )

    pages = int(info.get("Pages", "0"))
    require(pages > 0, "PDF has no pages")
    require(
        len(extracted_text.strip()) > 100,
        "PDF text extraction is unexpectedly empty",
    )

    size_match = re.search(
        r"Page size:\s*([0-9.]+)\s+x\s+([0-9.]+)\s+pts",
        info_text,
        flags=re.IGNORECASE,
    )
    require(size_match is not None, "could not parse PDF page size")
    width, height = map(float, size_match.groups())
    require(
        abs(width - A5_WIDTH_PT) <= PAGE_TOLERANCE_PT
        and abs(height - A5_HEIGHT_PT) <= PAGE_TOLERANCE_PT,
        f"PDF is not A5: {width} x {height} pt",
    )

    font_rows = []
    for line in fonts_text.splitlines()[2:]:
        parts = line.split()
        if len(parts) < 8:
            continue
        embedded = parts[-5].casefold()
        subset = parts[-4].casefold()
        font_rows.append((parts[0], embedded, subset))
    require(bool(font_rows), "pdffonts returned no font rows")
    not_embedded = [name for name, embedded, _ in font_rows if embedded != "yes"]
    not_subset = [name for name, _, subset in font_rows if subset != "yes"]
    require(not not_embedded, f"PDF has unembedded fonts: {not_embedded}")
    require(not not_subset, f"PDF has fonts that are not subset: {not_subset}")

    return {
        "path": str(pdf_path),
        "pages": pages,
        "page_size_pt": [width, height],
        "fonts": len(font_rows),
        "all_fonts_embedded_and_subset": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epub", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--essays-csv", type=Path)
    parser.add_argument("--expected-chapters", type=int)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--report-dir", type=Path, default=Path("build-reports"))
    args = parser.parse_args()

    try:
        csv_titles = read_csv_titles(args.essays_csv) if args.essays_csv else None
        expected_chapters = (
            len(csv_titles) if csv_titles is not None else args.expected_chapters
        )
        require(
            expected_chapters is not None,
            "provide --essays-csv or --expected-chapters",
        )

        if args.selection:
            manifest = json.loads(args.selection.read_text(encoding="utf-8"))
            expected_excluded = int(manifest["expected_exclusion_count"])
            require(args.audit is not None, "--audit is required with --selection")
            with args.audit.open(encoding="utf-8-sig", newline="") as handle:
                audit_rows = list(csv.DictReader(handle))
            require(
                len(audit_rows) == expected_excluded,
                f"audit row count mismatch: {len(audit_rows)} != {expected_excluded}",
            )
            require(
                all(row.get("Status") == "excluded" for row in audit_rows),
                "exclusion audit contains a non-excluded status",
            )
            if csv_titles is not None:
                included = {normalize(title) for title in csv_titles}
                excluded = {normalize(row["Title"]) for row in audit_rows}
                require(
                    not (included & excluded),
                    "included/excluded title sets overlap",
                )

        if args.summary:
            summary = json.loads(args.summary.read_text(encoding="utf-8"))
            require(
                int(summary["included_count"]) == int(expected_chapters),
                "build_summary included_count does not match expected chapters",
            )

        epub_result = check_epub(
            args.epub,
            args.title,
            args.author,
            int(expected_chapters),
            csv_titles,
        )
        pdf_result = check_pdf(args.pdf, args.title, args.author, args.report_dir)

        result = {"epub": epub_result, "pdf": pdf_result}
        args.report_dir.mkdir(parents=True, exist_ok=True)
        (args.report_dir / "validation.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (
        AssertionError,
        RuntimeError,
        OSError,
        KeyError,
        ValueError,
        zipfile.BadZipFile,
    ) as exc:
        print(f"output validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
