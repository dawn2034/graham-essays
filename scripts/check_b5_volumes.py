#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import fitz

B5_PT = (498.90, 708.66)
TOLERANCE_PT = 0.8

def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.translate(str.maketrans({"’":"'","‘":"'","“":'"',"”":'"',"\u00a0":" "}))
    return " ".join(value.split()).strip().casefold()

def canonical_title(value: str) -> str:
    return re.sub(r"^\d{1,4}\s+", "", normalize(value))

def fail(message: str) -> None:
    raise RuntimeError(message)

def run(*args: str) -> str:
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout

def parse_pdfinfo(text: str) -> dict[str, str]:
    result = {}
    for line in text.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip()
    return result

def check_fonts(path: Path) -> None:
    lines = [line for line in run("pdffonts", str(path)).splitlines()[2:] if line.strip()]
    if not lines:
        fail(f"{path} contains no detectable fonts")
    for line in lines:
        columns = line.split()
        if len(columns) < 9:
            fail(f"Could not parse pdffonts output for {path}: {line}")
        if columns[-5] != "yes" or columns[-4] != "yes":
            fail(f"A font is not embedded and subset in {path}: {line}")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--included", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, action="append", required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    volumes = plan["volumes"]
    if len(volumes) != 3 or len(args.pdf) != 3:
        fail("Exactly three planned volumes and three PDFs are required")

    with args.included.open(encoding="utf-8", newline="") as handle:
        all_rows = list(csv.DictReader(handle))
    all_expected = [canonical_title(row["Title"]) for row in all_rows]
    combined_actual = []
    actual_pages = []
    summary_volumes = []

    for volume, path in zip(volumes, args.pdf, strict=True):
        roman = volume["roman"]
        expected_titles = volume["titles"]
        expected_canonical = [canonical_title(title) for title in expected_titles]
        if not path.is_file() or path.stat().st_size == 0:
            fail(f"Volume PDF is missing or empty: {path}")

        info = parse_pdfinfo(run("pdfinfo", str(path)))
        if f"Volume {roman}" not in info.get("Title", ""):
            fail(f"Unexpected title metadata for {path}: {info.get('Title', 'missing')}")
        if info.get("Author") != "Paul Graham":
            fail(f"Unexpected author metadata for {path}: {info.get('Author', 'missing')}")
        if info.get("Encrypted", "").lower() != "no":
            fail(f"{path} must not be encrypted")
        check_fonts(path)

        with fitz.open(path) as document:
            page_count = document.page_count
            actual_pages.append(page_count)
            for page_number, page in enumerate(document, start=1):
                rect = page.rect
                if abs(rect.width-B5_PT[0]) > TOLERANCE_PT or abs(rect.height-B5_PT[1]) > TOLERANCE_PT:
                    fail(f"{path} page {page_number} is not ISO B5: {rect.width:.2f} x {rect.height:.2f} pt")
            outline = document.get_toc(simple=True)

        actual_titles = [canonical_title(item[1]) for item in outline]
        if actual_titles != expected_canonical:
            fail(f"{path} outline does not exactly match its planned essay range ({len(actual_titles)} outline entries vs {len(expected_titles)} planned)")
        combined_actual.extend(actual_titles)
        summary_volumes.append({
            "volume": volume["volume"],
            "roman": roman,
            "article_start": volume["article_start"],
            "article_end": volume["article_end"],
            "article_count": volume["article_count"],
            "first_title": volume["first_title"],
            "last_title": volume["last_title"],
            "estimated_content_pages": volume["estimated_content_pages"],
            "actual_pdf_pages": page_count,
            "file": path.as_posix(),
        })

    if combined_actual != all_expected:
        fail("The three volume outlines do not reconstruct essays.csv exactly")

    mean_pages = sum(actual_pages)/3
    spread = max(actual_pages)-min(actual_pages)
    allowed_spread = max(40, round(mean_pages*0.12))
    if spread > allowed_spread:
        fail(f"Three-volume page balance is outside tolerance: pages={actual_pages}, spread={spread}, allowed={allowed_spread}")

    summary = {
        "paper": "ISO B5",
        "strategy": plan["method"],
        "total_articles": len(all_rows),
        "volume_pages": actual_pages,
        "page_spread": spread,
        "allowed_page_spread": allowed_spread,
        "volumes": summary_volumes,
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print("B5 three-volume set validated: " + ", ".join(
        f"Vol. {v['roman']} {v['actual_pdf_pages']} pages" for v in summary_volumes
    ) + f"; spread {spread} pages.")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"volume validation error: {exc}", file=sys.stderr)
        raise SystemExit(1)
