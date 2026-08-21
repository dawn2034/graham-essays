#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

import fitz

ROMAN = ("I", "II", "III")

def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.translate(str.maketrans({"’":"'","‘":"'","“":'"',"”":'"',"\u00a0":" "}))
    return " ".join(value.split()).strip().casefold()

def canonical_title(value: str) -> str:
    return re.sub(r"^\d{1,4}\s+", "", normalize(value))

def fail(message: str) -> None:
    raise RuntimeError(message)

def choose_boundaries(page_spans: list[int]) -> tuple[int, int]:
    n = len(page_spans)
    if n < 3:
        fail("At least three essays are required to build three volumes")
    prefix = [0]
    for pages in page_spans:
        prefix.append(prefix[-1] + pages)
    total = prefix[-1]
    target = total / 3
    min_articles = max(1, min(12, n // 6))
    best = None
    for first in range(min_articles, n - 2 * min_articles + 1):
        for second in range(first + min_articles, n - min_articles + 1):
            parts = (prefix[first], prefix[second]-prefix[first], total-prefix[second])
            spread = max(parts)-min(parts)
            deviation = max(abs(value-target) for value in parts)
            article_spread = max(first, second-first, n-second)-min(first, second-first, n-second)
            score = (spread, deviation, article_spread)
            if best is None or score < best[0]:
                best = (score, first, second)
    if best is None:
        fail("Could not find valid three-volume boundaries")
    return best[1], best[2]

def main() -> int:
    parser = argparse.ArgumentParser(description="Plan a balanced three-volume B5 set from the full B5 typeset PDF.")
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--included", type=Path, required=True)
    parser.add_argument("--essays-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    with args.included.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    files = sorted(args.essays_dir.glob("*.md"))
    if len(rows) != len(files):
        fail(f"Included CSV and Markdown file counts differ: {len(rows)} rows vs {len(files)} files")

    with fitz.open(args.pdf) as document:
        raw_outline = document.get_toc(simple=True)
        page_count = document.page_count
    if len(raw_outline) != len(rows):
        fail(f"Full B5 outline and included CSV counts differ: {len(raw_outline)} vs {len(rows)}")

    for index, (row, outline_item) in enumerate(zip(rows, raw_outline, strict=True), start=1):
        if canonical_title(row["Title"]) != canonical_title(outline_item[1]):
            fail(f"Outline title mismatch at essay {index}: {row['Title']!r} vs {outline_item[1]!r}")

    starts = [int(item[2]) for item in raw_outline]
    if any(start < 1 or start > page_count for start in starts):
        fail("Full B5 outline contains an invalid page destination")
    if starts != sorted(starts):
        fail("Full B5 outline page destinations are not ordered")

    page_spans = [
        (starts[i+1] if i+1 < len(starts) else page_count+1) - starts[i]
        for i in range(len(starts))
    ]
    if any(span <= 0 for span in page_spans):
        fail("At least one essay has a non-positive page span")

    first_cut, second_cut = choose_boundaries(page_spans)
    ranges = ((0, first_cut), (first_cut, second_cut), (second_cut, len(rows)))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    volumes = []

    for volume_index, (start, end) in enumerate(ranges, start=1):
        roman = ROMAN[volume_index-1]
        volume_files = files[start:end]
        volume_rows = rows[start:end]
        estimated_pages = sum(page_spans[start:end])

        file_list = args.output_dir / f"volume-{volume_index}-files.txt"
        file_list.write_text("".join(f"{path.as_posix()}\n" for path in volume_files), encoding="utf-8")

        metadata = args.output_dir / f"volume-{volume_index}-metadata.yaml"
        metadata.write_text(
            "---\n"
            f'title: "Paul Graham: Selected Essays — Volume {roman}"\n'
            f'subtitle: "Volume {roman} of III"\n'
            'author: "Paul Graham"\n'
            "lang: en\n"
            "...\n",
            encoding="utf-8",
        )

        volumes.append({
            "volume": volume_index,
            "roman": roman,
            "article_start": start+1,
            "article_end": end,
            "article_count": end-start,
            "first_title": volume_rows[0]["Title"],
            "last_title": volume_rows[-1]["Title"],
            "estimated_content_pages": estimated_pages,
            "files_manifest": file_list.as_posix(),
            "metadata_file": metadata.as_posix(),
            "titles": [row["Title"] for row in volume_rows],
        })

    plan = {
        "method": "Preserve reading order and split only at essay boundaries; choose boundaries that minimize the spread in actual B5 chapter page spans measured from the full single-volume PDF.",
        "source_pdf": args.pdf.as_posix(),
        "source_pdf_pages": page_count,
        "included_essay_count": len(rows),
        "estimated_content_pages": sum(page_spans),
        "volumes": volumes,
    }
    (args.output_dir/"volume-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print("B5 three-volume plan: " + ", ".join(
        f"Vol. {v['roman']} {v['article_count']} essays / ~{v['estimated_content_pages']} content pages"
        for v in volumes
    ))
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"volume planning error: {exc}", file=sys.stderr)
        raise SystemExit(1)
