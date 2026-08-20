#!/usr/bin/env python3
"""Download the selected Paul Graham essay collection.

The source index remains Paul Graham's official essay page. Selection is
controlled by selection.json: configured titles are excluded, while new titles
are included by default. The script fails closed if a configured exclusion can
no longer be matched, preventing a silently incorrect edition.
"""

from __future__ import annotations

import csv
import json
import os
import re as std_re
import shutil
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

import dateparser
import html2text
import regex as re
import requests
from bs4 import BeautifulSoup
from htmldate import find_date
from unidecode import unidecode

BASE_URL = "https://paulgraham.com/"
INDEX_PATH = "articles.html"
SELECTION_FILE = Path("selection.json")
ESSAYS_DIR = Path("essays")
INCLUDED_CSV = Path("essays.csv")
EXCLUDED_CSV = Path("excluded_essays.csv")
SUMMARY_JSON = Path("edition-summary.json")
USER_AGENT = (
    "graham-essays-selected-edition/1.0 "
    "(+https://github.com/dawn2034/graham-essays)"
)


@dataclass(frozen=True)
class EssayLink:
    source_no: int
    title: str
    url: str


def normalize_title(value: str) -> str:
    """Normalize typography, punctuation and case for stable title matching."""
    value = unicodedata.normalize("NFKC", value)
    value = (
        value.replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u00a0", " ")
    )
    value = value.casefold()
    value = std_re.sub(r"[^\w]+", " ", value, flags=std_re.UNICODE)
    return " ".join(value.split())


def load_selection(path: Path = SELECTION_FILE) -> tuple[dict, dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    flattened: list[str] = [
        title for titles in data.get("groups", {}).values() for title in titles
    ]
    expected = int(data.get("expected_exclusion_count", 0))
    if expected != len(flattened):
        raise RuntimeError(
            f"selection.json says {expected} exclusions but contains {len(flattened)}"
        )

    normalized: dict[str, str] = {}
    for title in flattened:
        key = normalize_title(title)
        if key in normalized:
            raise RuntimeError(
                f"duplicate normalized exclusion: {title!r} and {normalized[key]!r}"
            )
        normalized[key] = title
    return data, normalized


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def fetch_text(session: requests.Session, url: str, attempts: int = 4) -> str:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = session.get(url, timeout=(15, 45))
            response.raise_for_status()
            if response.encoding is None or response.encoding.lower() in {
                "iso-8859-1",
                "ascii",
            }:
                response.encoding = response.apparent_encoding or "utf-8"
            return response.text
        except (requests.RequestException, UnicodeError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(0.8 * attempt)
    raise RuntimeError(f"failed to fetch {url}: {last_error}")


def parse_main_page(session: requests.Session) -> list[EssayLink]:
    html = fetch_text(session, urljoin(BASE_URL, INDEX_PATH))
    soup = BeautifulSoup(html, "html.parser")
    chapter_links: list[tuple[str, str]] = []

    # Paul Graham's index marks each canonical essay row with a tiny icon. This
    # avoids accidentally including the three recommendations repeated at top.
    for td in soup.select("table > tr > td > table > tr > td"):
        img = td.find("img")
        if not img:
            continue
        try:
            width = int(img.get("width", 0))
            height = int(img.get("height", 0))
        except (TypeError, ValueError):
            continue
        if width > 15 or height > 15:
            continue
        font = td.find("font")
        anchor = font.find("a") if font else None
        if not anchor or not anchor.get("href"):
            continue
        title = " ".join(anchor.get_text(" ", strip=True).split())
        if title:
            chapter_links.append((title, urljoin(BASE_URL, anchor["href"])))

    # The public page is newest first; books read more naturally oldest first.
    chapter_links.reverse()
    return [
        EssayLink(source_no=i, title=title, url=url)
        for i, (title, url) in enumerate(chapter_links, start=1)
    ]


def configure_html2text() -> html2text.HTML2Text:
    converter = html2text.HTML2Text()
    converter.ignore_images = True
    converter.ignore_tables = True
    converter.escape_all = True
    converter.reference_links = True
    converter.mark_code = True
    converter.body_width = 0
    return converter


def convert_to_pandoc_footnotes(text: str, essay_id: str) -> str:
    """Convert PG's numbered Notes section to globally unique Pandoc footnotes."""
    notes_section_pattern = r"\*\*Notes?\*\*.*?(?=\n\s*\*\*|\Z)"
    notes_match = re.search(notes_section_pattern, text, re.DOTALL | re.IGNORECASE)
    if not notes_match:
        return text

    notes_content = notes_match.group(0)
    footnote_pattern = r"\[(\d+)\]\s*(.*?)(?=\s*\[\d+\]|\s*$)"
    footnotes = re.findall(footnote_pattern, notes_content, re.DOTALL)
    definitions: dict[str, str] = {}
    for note_num, content in footnotes:
        content = re.sub(r"\s+", " ", content).strip()
        if content:
            definitions[note_num] = content
    if not definitions:
        return text

    text = re.sub(notes_section_pattern, "", text, flags=re.DOTALL | re.IGNORECASE)
    for note_num in definitions:
        # Do not rewrite links/footnotes that already use a caret.
        text = re.sub(
            rf"(?<!\^)\[{re.escape(note_num)}\]",
            f"[^{essay_id}-{note_num}]",
            text,
        )
    definitions_md = "\n\n".join(
        f"[^{essay_id}-{note_num}]: {definitions[note_num]}"
        for note_num in sorted(definitions, key=int)
    )
    return text.rstrip() + "\n\n" + definitions_md + "\n"


def clean_markdown(raw_html: str, converter: html2text.HTML2Text, essay_id: str) -> str:
    markdown = converter.handle(raw_html)
    markdown = markdown.replace("[](index.html)  \n  \n", "")
    markdown = markdown.replace("\r\n", "\n").replace("\r", "\n")
    markdown = std_re.sub(r"[ \t]+\n", "\n", markdown)
    markdown = std_re.sub(r"\n{3,}", "\n\n", markdown)
    markdown = convert_to_pandoc_footnotes(markdown.strip(), essay_id)
    return markdown.strip() + "\n"


def extract_date(raw_html: str) -> str:
    match = std_re.search(
        r"<font[^>]*>\s*((?:January|February|March|April|May|June|July|"
        r"August|September|October|November|December)\s+\d{4})",
        raw_html,
        std_re.IGNORECASE,
    )
    if match:
        parsed = dateparser.parse(match.group(1))
        if parsed:
            return parsed.strftime("%Y-%m-%d")
    candidate = find_date(raw_html)
    return candidate or ""


def slugify(title: str) -> str:
    ascii_title = unidecode(title).casefold()
    slug = std_re.sub(r"[^a-z0-9]+", "-", ascii_title).strip("-")
    return slug[:96] or "essay"


def write_csv(path: Path, header: Iterable[str], rows: Iterable[Iterable[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(list(header))
        writer.writerows(rows)


def main() -> int:
    selection, excluded_config = load_selection()
    session = make_session()
    links = parse_main_page(session)

    minimum_source_count = int(selection.get("minimum_source_count", 0))
    if len(links) < minimum_source_count:
        raise RuntimeError(
            f"official index returned {len(links)} essays; expected at least "
            f"{minimum_source_count}"
        )

    by_normalized_title: dict[str, EssayLink] = {}
    duplicate_titles: list[str] = []
    for link in links:
        key = normalize_title(link.title)
        if key in by_normalized_title:
            duplicate_titles.append(link.title)
        by_normalized_title[key] = link
    if duplicate_titles:
        raise RuntimeError(f"duplicate titles on source index: {duplicate_titles}")

    missing = sorted(set(excluded_config) - set(by_normalized_title))
    if missing:
        readable = [excluded_config[key] for key in missing]
        raise RuntimeError(f"configured exclusions not found on source index: {readable}")

    excluded_links = [
        link for link in links if normalize_title(link.title) in excluded_config
    ]
    included_links = [
        link for link in links if normalize_title(link.title) not in excluded_config
    ]
    if len(excluded_links) != int(selection["expected_exclusion_count"]):
        raise RuntimeError(
            f"matched {len(excluded_links)} excluded essays; expected "
            f"{selection['expected_exclusion_count']}"
        )

    if ESSAYS_DIR.exists():
        shutil.rmtree(ESSAYS_DIR)
    ESSAYS_DIR.mkdir(parents=True)

    write_csv(
        EXCLUDED_CSV,
        ["Source no.", "Title", "URL", "Configured title"],
        (
            [
                link.source_no,
                link.title,
                link.url,
                excluded_config[normalize_title(link.title)],
            ]
            for link in excluded_links
        ),
    )

    included_rows: list[list[object]] = []
    failures: list[dict[str, object]] = []
    converter = configure_html2text()

    for edition_no, link in enumerate(included_links, start=1):
        essay_id = str(edition_no).zfill(3)
        try:
            raw_html = fetch_text(session, link.url)
            markdown = clean_markdown(raw_html, converter, essay_id)
            path = ESSAYS_DIR / f"{essay_id}_{slugify(link.title)}.md"
            path.write_text(
                f"# {link.title}\n\n{markdown}",
                encoding="utf-8",
            )
            date = extract_date(raw_html)
            included_rows.append([essay_id, link.title, date, link.url])
            print(f"OK {essay_id} {link.title}")
        except Exception as exc:  # continue to produce a complete failure report
            failures.append(
                {
                    "edition_no": edition_no,
                    "source_no": link.source_no,
                    "title": link.title,
                    "url": link.url,
                    "error": str(exc),
                }
            )
            print(f"ERROR {essay_id} {link.title}: {exc}", file=sys.stderr)
        time.sleep(0.08)

    write_csv(
        INCLUDED_CSV,
        ["Article no.", "Title", "Date", "URL"],
        included_rows,
    )

    summary = {
        "edition": selection.get("edition", "Selected Essays"),
        "source_index": urljoin(BASE_URL, INDEX_PATH),
        "source_count": len(links),
        "configured_exclusion_count": len(excluded_config),
        "matched_exclusion_count": len(excluded_links),
        "included_count": len(included_links),
        "downloaded_count": len(included_rows),
        "failures": failures,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    SUMMARY_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if failures:
        print(f"Build stopped: {len(failures)} essays failed to download.", file=sys.stderr)
        return 1
    if len(included_rows) != len(included_links):
        print("Build stopped: included CSV is incomplete.", file=sys.stderr)
        return 1

    print(
        f"Selected edition: {len(included_rows)} included, "
        f"{len(excluded_links)} excluded, {len(links)} total."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
