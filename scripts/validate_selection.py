#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
import unicodedata
from pathlib import Path


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.translate(
        str.maketrans(
            {"’": "'", "‘": "'", "“": '"', "”": '"', "\u00a0": " "}
        )
    )
    return " ".join(value.split()).strip().casefold()


def fail(message: str, details: list[str] | None = None) -> int:
    print(message, file=sys.stderr)
    for detail in details or []:
        print(f"  - {detail}", file=sys.stderr)
    return 1


def main() -> int:
    selection_path = Path("selection.json")
    essays_path = Path("essays.csv")
    audit_path = Path("excluded_essays.csv")
    essays_dir = Path("essays")

    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    configured_rows = selection.get("excluded", [])
    expected_exclusion_count = selection.get(
        "expected_exclusion_count", len(configured_rows)
    )
    if len(configured_rows) != expected_exclusion_count:
        return fail(
            "The exclusion manifest count does not match its declared boundary.",
            [
                f"declared={expected_exclusion_count}",
                f"configured={len(configured_rows)}",
            ],
        )

    excluded = {normalize(item["title"]): item for item in configured_rows}
    if len(excluded) != len(configured_rows):
        return fail("Duplicate titles exist in the exclusion manifest.")

    with essays_path.open(encoding="utf-8", newline="") as handle:
        included_rows = list(csv.DictReader(handle))
    included = {normalize(row["Title"]): row for row in included_rows}
    if len(included) != len(included_rows):
        return fail("Duplicate titles exist in the included collection.")

    overlap = sorted(set(excluded) & set(included))
    if overlap:
        return fail(
            "Excluded essays leaked into the selected collection.",
            [included[key]["Title"] for key in overlap],
        )

    with audit_path.open(encoding="utf-8", newline="") as handle:
        audit_rows = list(csv.DictReader(handle))
    if len(audit_rows) != expected_exclusion_count:
        return fail(
            "The exclusion audit has the wrong number of rows.",
            [f"expected={expected_exclusion_count}", f"actual={len(audit_rows)}"],
        )

    found = {
        normalize(row["Title"])
        for row in audit_rows
        if row["Status"] == "excluded"
    }
    missing = sorted(set(excluded) - found)
    if missing:
        return fail(
            "Configured exclusions were not found on the live index.",
            [excluded[key]["title"] for key in missing],
        )

    unexpected_statuses = [
        f"{row['Title']}: {row['Status']}"
        for row in audit_rows
        if row["Status"] != "excluded"
    ]
    if unexpected_statuses:
        return fail(
            "The exclusion audit contains unmatched entries.", unexpected_statuses
        )

    numbers = [int(row["Article no."]) for row in included_rows]
    expected_numbers = list(range(1, len(numbers) + 1))
    if numbers != expected_numbers:
        return fail("Article numbers are not contiguous.")

    markdown_files = sorted(essays_dir.glob("*.md"))
    if len(markdown_files) != len(included_rows):
        return fail(
            "The Markdown file count does not match essays.csv.",
            [f"markdown={len(markdown_files)}", f"csv={len(included_rows)}"],
        )

    print(
        f"Selection validated: {len(included_rows)} included, "
        f"{len(found)} excluded, no overlap."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
