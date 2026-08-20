#!/usr/bin/env python3
"""Apply the exact exclusion manifest to a complete downloaded collection.

The upstream scraper writes a chronologically numbered ``essays/`` directory
and ``essays.csv``. This script performs a fail-closed, auditable transform:

1. match every configured exclusion against the downloaded index;
2. rebuild the selected Markdown directory with contiguous numbering;
3. rewrite the included CSV;
4. emit an exclusion audit and machine-readable build summary.

No fuzzy matching is used beyond typography normalization. A missing or
ambiguous title is a build error, because silently retaining an essay would
violate the declared edition boundary.
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path
from typing import Any, NoReturn

SELECTION_PATH = Path("selection.json")
ESSAYS_CSV = Path("essays.csv")
ESSAYS_DIR = Path("essays")
AUDIT_CSV = Path("excluded_essays.csv")
SUMMARY_JSON = Path("build_summary.json")
TEMP_DIR = Path("essays.selected.tmp")
TEMP_CSV = Path("essays.selected.csv.tmp")

CSV_FIELDS = ["Article no.", "Title", "Date", "URL"]
AUDIT_FIELDS = ["Title", "Category", "URL", "Source article no.", "Status"]


def normalize_title(value: str) -> str:
    """Normalize harmless typographic differences without fuzzy matching."""
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


def die(message: str, details: list[str] | None = None) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    for detail in details or []:
        print(f"  - {detail}", file=sys.stderr)
    raise SystemExit(1)


def load_manifest() -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    if not SELECTION_PATH.is_file():
        die(f"selection manifest not found: {SELECTION_PATH}")

    data = json.loads(SELECTION_PATH.read_text(encoding="utf-8"))
    entries = data.get("excluded")
    if not isinstance(entries, list):
        die("selection.json must contain an 'excluded' list")

    expected = data.get("expected_exclusion_count", len(entries))
    if expected != len(entries):
        die(
            "configured exclusion count differs from expected_exclusion_count",
            [f"expected={expected}", f"configured={len(entries)}"],
        )

    by_title: dict[str, dict[str, str]] = {}
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            die(f"manifest entry {index} is not an object")
        title = str(entry.get("title", "")).strip()
        category = str(entry.get("category", "uncategorized")).strip()
        if not title:
            die(f"manifest entry {index} has no title")
        key = normalize_title(title)
        if key in by_title:
            die("duplicate normalized title in selection.json", [title])
        by_title[key] = {"title": title, "category": category}

    return data, by_title


def read_source_rows() -> list[dict[str, str]]:
    if not ESSAYS_CSV.is_file():
        die(f"source CSV not found: {ESSAYS_CSV}")
    if not ESSAYS_DIR.is_dir():
        die(f"source essay directory not found: {ESSAYS_DIR}")

    with ESSAYS_CSV.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != CSV_FIELDS:
            die(
                "unexpected essays.csv columns",
                [f"expected={CSV_FIELDS}", f"actual={reader.fieldnames}"],
            )
        rows = [
            {field: (row.get(field) or "").strip() for field in CSV_FIELDS}
            for row in reader
        ]

    if not rows:
        die("source collection is empty")

    seen_titles: dict[str, str] = {}
    seen_numbers: set[str] = set()
    duplicates: list[str] = []
    for row in rows:
        title = row["Title"]
        article_no = row["Article no."]
        if not title or not article_no:
            die("essays.csv contains a blank title or article number", [repr(row)])
        key = normalize_title(title)
        if key in seen_titles:
            duplicates.append(f"{seen_titles[key]} / {title}")
        seen_titles[key] = title
        if article_no in seen_numbers:
            die("duplicate source article number", [article_no])
        seen_numbers.add(article_no)

    if duplicates:
        die("duplicate normalized titles in source collection", duplicates)
    return rows


def find_source_file(article_no: str) -> Path:
    candidates = sorted(ESSAYS_DIR.glob(f"{article_no}_*.md"))
    if len(candidates) != 1:
        die(
            "source Markdown file lookup is ambiguous",
            [f"article={article_no}", *[str(path) for path in candidates]],
        )
    return candidates[0]


def rewrite_heading(content: str, article_no: str, title: str, source: Path) -> str:
    pattern = re.compile(r"^#\s+\d+\s+.*$", flags=re.MULTILINE)
    replacement = f"# {article_no} {title}"
    rewritten, count = pattern.subn(lambda _: replacement, content, count=1)
    if count != 1:
        die("could not rewrite the essay's first-level heading", [str(source)])
    return rewritten


def write_audit(
    manifest_order: list[dict[str, str]],
    matched: dict[str, dict[str, str]],
) -> None:
    with AUDIT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_FIELDS)
        writer.writeheader()
        for item in manifest_order:
            key = normalize_title(item["title"])
            source = matched[key]
            writer.writerow(
                {
                    "Title": source["Title"],
                    "Category": item["category"],
                    "URL": source["URL"],
                    "Source article no.": source["Article no."],
                    "Status": "excluded",
                }
            )


def main() -> int:
    manifest, excluded_by_title = load_manifest()
    source_rows = read_source_rows()

    source_by_title = {normalize_title(row["Title"]): row for row in source_rows}
    missing_keys = sorted(set(excluded_by_title) - set(source_by_title))
    if missing_keys:
        die(
            "configured exclusions were not found in the downloaded index",
            [excluded_by_title[key]["title"] for key in missing_keys],
        )

    matched = {key: source_by_title[key] for key in excluded_by_title}
    manifest_order = [
        {
            "title": str(item["title"]),
            "category": str(item.get("category", "uncategorized")),
        }
        for item in manifest["excluded"]
    ]

    included_rows = [
        row
        for row in source_rows
        if normalize_title(row["Title"]) not in excluded_by_title
    ]
    if len(source_rows) - len(included_rows) != len(excluded_by_title):
        die(
            "source/exclusion arithmetic is inconsistent",
            [
                f"source={len(source_rows)}",
                f"included={len(included_rows)}",
                f"configured_excluded={len(excluded_by_title)}",
            ],
        )

    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)
    if TEMP_CSV.exists():
        TEMP_CSV.unlink()
    TEMP_DIR.mkdir(parents=True)

    rewritten_rows: list[dict[str, str]] = []
    try:
        for new_index, row in enumerate(included_rows, start=1):
            new_no = f"{new_index:03d}"
            source_path = find_source_file(row["Article no."])
            suffix = source_path.name.split("_", 1)[1]
            target_path = TEMP_DIR / f"{new_no}_{suffix}"
            content = source_path.read_text(encoding="utf-8")
            target_path.write_text(
                rewrite_heading(content, new_no, row["Title"], source_path),
                encoding="utf-8",
            )
            rewritten_rows.append(
                {
                    "Article no.": new_no,
                    "Title": row["Title"],
                    "Date": row["Date"],
                    "URL": row["URL"],
                }
            )

        with TEMP_CSV.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rewritten_rows)

        # Replace the full source set only after every file has been prepared.
        shutil.rmtree(ESSAYS_DIR)
        TEMP_DIR.replace(ESSAYS_DIR)
        TEMP_CSV.replace(ESSAYS_CSV)
    except BaseException:
        if TEMP_DIR.exists():
            shutil.rmtree(TEMP_DIR)
        if TEMP_CSV.exists():
            TEMP_CSV.unlink()
        raise

    write_audit(manifest_order, matched)
    summary = {
        "edition": manifest.get("edition", "Selected Essays"),
        "source_index_count": len(source_rows),
        "configured_exclusion_count": len(excluded_by_title),
        "excluded_count": len(matched),
        "included_count": len(rewritten_rows),
    }
    SUMMARY_JSON.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(
        "Selection applied: "
        f"{summary['source_index_count']} source items -> "
        f"{summary['included_count']} included + {summary['excluded_count']} excluded."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
