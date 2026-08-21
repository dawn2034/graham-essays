#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import fitz

B5_PT = (498.90, 708.66)
TOLERANCE_PT = 0.8


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
    return re.sub(r"^\d{1,4}\s+", "", normalize(value))


def run(*args: str) -> str:
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout


def parse_pdfinfo(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def check_pdf(path: Path, volume: dict) -> int:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"Missing or empty themed volume PDF: {path}")

    info = parse_pdfinfo(run("pdfinfo", str(path)))
    expected_title = (
        f"Paul Graham: Selected Essays — {volume['label']}: {volume['subtitle']}"
    )
    if info.get("Title") != expected_title:
        raise RuntimeError(
            f"Unexpected title metadata for {path}: {info.get('Title')!r}"
        )
    if info.get("Author") != "Paul Graham":
        raise RuntimeError(f"Unexpected author metadata for {path}")
    if info.get("Encrypted", "").lower() != "no":
        raise RuntimeError(f"Themed PDF must not be encrypted: {path}")

    match = re.search(r"([0-9.]+) x ([0-9.]+) pts", info.get("Page size", ""))
    if not match:
        raise RuntimeError(f"Could not parse page size for {path}")
    width, height = map(float, match.groups())
    if abs(width - B5_PT[0]) > TOLERANCE_PT or abs(height - B5_PT[1]) > TOLERANCE_PT:
        raise RuntimeError(f"Themed PDF is not ISO B5: {path}")

    font_lines = [
        line for line in run("pdffonts", str(path)).splitlines()[2:] if line.strip()
    ]
    if not font_lines:
        raise RuntimeError(f"No detectable fonts in {path}")
    for line in font_lines:
        columns = line.split()
        if len(columns) < 9 or columns[-5] != "yes" or columns[-4] != "yes":
            raise RuntimeError(f"Font is not embedded/subset in {path}: {line}")

    expected_titles = [canonical_title(title) for title in volume["titles"]]
    with fitz.open(path) as document:
        if document.page_count < 2:
            raise RuntimeError(f"Suspiciously short themed volume: {path}")
        first_page_images = document[0].get_images(full=True)
        if not first_page_images:
            raise RuntimeError(f"Generated cover artwork is missing from {path}")
        for index, page in enumerate(document, start=1):
            rect = page.rect
            if (
                abs(rect.width - B5_PT[0]) > TOLERANCE_PT
                or abs(rect.height - B5_PT[1]) > TOLERANCE_PT
            ):
                raise RuntimeError(f"Page {index} of {path} is not ISO B5")
        outline = document.get_toc(simple=True)
        actual_titles = [canonical_title(item[1]) for item in outline]
        if actual_titles != expected_titles:
            raise RuntimeError(f"PDF outline does not match theme plan: {path}")
        return document.page_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--included", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--vol1", type=Path, required=True)
    parser.add_argument("--vol2", type=Path, required=True)
    parser.add_argument("--vol3", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    args = parser.parse_args()

    with args.included.open(encoding="utf-8", newline="") as handle:
        all_titles = [row["Title"] for row in csv.DictReader(handle)]
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    volumes = plan["volumes"]
    if len(volumes) != 3:
        raise RuntimeError(f"Expected 3 themed volumes, found {len(volumes)}")

    pdfs = [args.vol1, args.vol2, args.vol3]
    page_counts: dict[str, int] = {}
    combined_titles: list[str] = []
    for pdf, volume in zip(pdfs, volumes):
        page_counts[volume["slug"]] = check_pdf(pdf, volume)
        combined_titles.extend(volume["titles"])

    source = [canonical_title(title) for title in all_titles]
    combined = [canonical_title(title) for title in combined_titles]
    if Counter(source) != Counter(combined):
        raise RuntimeError(
            "The themed set does not cover essays.csv exactly once: "
            f"source={len(source)}, themed={len(combined)}"
        )

    # Theme grouping intentionally changes cross-volume order. Inside each volume,
    # however, the original reading order must be preserved.
    positions = {title: index for index, title in enumerate(source)}
    for volume in volumes:
        indices = [positions[canonical_title(title)] for title in volume["titles"]]
        if indices != sorted(indices):
            raise RuntimeError(
                f"Original relative order changed inside {volume['label']}"
            )

    summary = {
        "strategy": "theme-oriented",
        "included_essay_count": len(all_titles),
        "volumes": [
            {
                "slug": volume["slug"],
                "label": volume["label"],
                "subtitle": volume["subtitle"],
                "essay_count": volume["essay_count"],
                "page_count": page_counts[volume["slug"]],
                "first_title": volume["first_title"],
                "last_title": volume["last_title"],
            }
            for volume in volumes
        ],
    }
    args.summary_out.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Themed B5 three-volume set validated successfully.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"validation error: {exc}", file=sys.stderr)
        raise SystemExit(1)
