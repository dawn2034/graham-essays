"""Download a curated collection of Paul Graham essays."""

from __future__ import annotations

import csv
import json
import shutil
import time
import unicodedata
from pathlib import Path
from urllib.parse import urljoin

import html2text
import regex as re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from dateparser import parse as parse_date
from htmldate import find_date


BASE_URL = "https://paulgraham.com/"
ARTICLES_INDEX = "articles.html"
ESSAYS_DIR = Path("essays")
ESSAYS_CSV = Path("essays.csv")
EXCLUDED_CSV = Path("excluded_essays.csv")
SELECTION_FILE = Path("selection.json")
BUILD_SUMMARY = Path("build_summary.json")
REQUEST_TIMEOUT = 60
REQUEST_DELAY_SECONDS = 0.10


def normalize_title(value: str) -> str:
    """Normalize title typography and whitespace for stable matching."""
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
    return re.sub(r"\s+", " ", value).strip().casefold()


def load_selection(path: Path) -> tuple[dict, dict[str, dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("excluded", [])
    expected_count = int(data.get("expected_exclusion_count", len(rows)))
    if len(rows) != expected_count:
        raise ValueError(
            f"Selection boundary mismatch in {path}: "
            f"declared={expected_count}, configured={len(rows)}"
        )

    excluded: dict[str, dict] = {}
    for item in rows:
        title = item.get("title", "").strip()
        category = item.get("category", "uncategorized").strip()
        if not title:
            raise ValueError("Every excluded selection entry must have a title")

        key = normalize_title(title)
        if key in excluded:
            raise ValueError(f"Duplicate exclusion in {path}: {title}")
        excluded[key] = {"title": title, "category": category}

    return data, excluded


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "User-Agent": (
                "graham-essays-curated/1.0 "
                "(+https://github.com/dawn2034/graham-essays)"
            )
        }
    )
    return session


def parse_main_page(
    session: requests.Session, base_url: str, articles_url: str
) -> list[dict[str, str]]:
    if not base_url.endswith("/"):
        raise ValueError(f"Base URL must end with a slash: {base_url}")

    response = session.get(urljoin(base_url, articles_url), timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    chapter_links: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    # Paul Graham's index uses tiny image bullets in nested tables. Restricting
    # extraction to those cells avoids navigation and decorative links.
    for td in soup.select("table > tr > td > table > tr > td"):
        img = td.find("img")
        if not img:
            continue

        try:
            is_bullet = int(img.get("width", 0)) <= 15 and int(
                img.get("height", 0)
            ) <= 15
        except (TypeError, ValueError):
            is_bullet = False

        if not is_bullet:
            continue

        font = td.find("font")
        a_tag = font.find("a") if font else None
        if not a_tag or not a_tag.get("href"):
            continue

        url = urljoin(base_url, a_tag["href"])
        title = a_tag.get_text(" ", strip=True)
        if not title or url in seen_urls:
            continue

        seen_urls.add(url)
        chapter_links.append({"link": url, "title": title})

    if not chapter_links:
        raise RuntimeError("No essay links were found on Paul Graham's index page")

    return chapter_links


def make_html_converter() -> html2text.HTML2Text:
    converter = html2text.HTML2Text()
    converter.ignore_images = True
    converter.ignore_tables = True
    converter.escape_all = True
    converter.reference_links = True
    converter.mark_code = True
    return converter


def convert_to_pandoc_footnotes(text: str | bytes, essay_id: str = "") -> bytes:
    if isinstance(text, bytes):
        text = text.decode("utf-8")

    notes_section_pattern = r"\*\*Notes?\*\*.*?(?=\n\s*\*\*|\Z)"
    notes_match = re.search(notes_section_pattern, text, re.DOTALL | re.IGNORECASE)

    if not notes_match:
        return text.encode("utf-8")

    notes_content = notes_match.group(0)
    footnote_pattern = r"\[(\d+)\]\s*(.*?)(?=\s*\[\d+\]|\s*$)"
    footnotes = re.findall(footnote_pattern, notes_content, re.DOTALL)

    if not footnotes:
        return text.encode("utf-8")

    footnote_definitions: dict[str, str] = {}
    for note_num, note_content in footnotes:
        note_content = re.sub(r"\s+", " ", note_content.strip()).strip()
        if note_content:
            footnote_definitions[note_num] = note_content

    text = re.sub(notes_section_pattern, "", text, flags=re.DOTALL | re.IGNORECASE)

    prefix = f"{essay_id}-" if essay_id else ""
    for note_num in footnote_definitions:
        text = re.sub(rf"\[{note_num}\]", f"[^{prefix}{note_num}]", text)

    if footnote_definitions:
        definitions = [
            f"[^{prefix}{note_num}]: {footnote_definitions[note_num]}"
            for note_num in sorted(footnote_definitions, key=int)
        ]
        text += "\n\n" + "\n\n".join(definitions)

    return text.encode("utf-8")


def detect_date(content: str) -> str | None:
    pg_date_match = re.search(
        r"<font[^>]*>((?:January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+\d{4})",
        content,
        re.IGNORECASE,
    )
    if pg_date_match:
        parsed_date = parse_date(pg_date_match.group(1))
        if parsed_date:
            return parsed_date.strftime("%Y-%m-%d")

    return find_date(content)


def clean_markdown(parsed: str) -> bytes:
    parsed = parsed.replace("[](index.html)  \n  \n", "")
    normalized_lines = [
        (
            paragraph.replace("\n", " ")
            if re.match(
                r"^[\p{Z}\s]*(?:[^\p{Z}\s][\p{Z}\s]*){5,100}$", paragraph
            )
            else "\n" + paragraph + "\n"
        )
        for paragraph in parsed.split("\n")
    ]
    return " ".join(normalized_lines).encode("utf-8")


def safe_slug(title: str) -> str:
    slug = unicodedata.normalize("NFKD", title)
    slug = re.sub(r"[^\p{L}\p{N}]+", "_", slug).strip("_").lower()
    return slug or "essay"


def write_exclusion_audit(
    configured: dict[str, dict],
    matched: dict[str, dict[str, str]],
) -> None:
    with EXCLUDED_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["Title", "Category", "URL", "Status"],
        )
        writer.writeheader()
        for key, item in configured.items():
            match = matched.get(key)
            writer.writerow(
                {
                    "Title": match["title"] if match else item["title"],
                    "Category": item["category"],
                    "URL": match["link"] if match else "",
                    "Status": "excluded" if match else "not_found_on_index",
                }
            )


def main() -> None:
    # A fetch target must be reproducible on its own. Remove stale article files
    # so a previously included title cannot survive a changed selection.
    if ESSAYS_DIR.exists():
        shutil.rmtree(ESSAYS_DIR)
    ESSAYS_DIR.mkdir(parents=True, exist_ok=True)
    for generated_csv in (ESSAYS_CSV, EXCLUDED_CSV, BUILD_SUMMARY):
        if generated_csv.exists():
            generated_csv.unlink()

    selection, excluded = load_selection(SELECTION_FILE)
    session = make_session()
    all_entries = parse_main_page(session, BASE_URL, ARTICLES_INDEX)

    selected_entries: list[dict[str, str]] = []
    matched_exclusions: dict[str, dict[str, str]] = {}

    for entry in all_entries:
        key = normalize_title(entry["title"])
        if key in excluded:
            matched_exclusions[key] = entry
            print(f"⏭ Excluding: {entry['title']}")
        else:
            selected_entries.append(entry)

    write_exclusion_audit(excluded, matched_exclusions)

    missing = [
        item["title"]
        for key, item in excluded.items()
        if key not in matched_exclusions
    ]
    if missing:
        details = "\n".join(f"  - {title}" for title in missing)
        raise RuntimeError(
            "Configured exclusions were not found on the current index:\n"
            + details
        )

    # The source index is newest-first; reverse it for chronological reading.
    toc = list(reversed(selected_entries))

    with ESSAYS_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["Article no.", "Title", "Date", "URL"]
        )
        writer.writeheader()

    article_no = 0
    failures: list[tuple[str, str, str]] = []
    for entry in toc:
        article_no += 1
        article_id = str(article_no).zfill(3)
        url = entry["link"].replace(
            "http://www.paulgraham.com/https://", "https://"
        )
        title = entry["title"]

        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or response.encoding
            content = response.text

            parsed = make_html_converter().handle(content)
            markdown_path = ESSAYS_DIR / f"{article_id}_{safe_slug(title)}.md"
            encoded = clean_markdown(parsed)
            processed = convert_to_pandoc_footnotes(encoded, article_id)

            with markdown_path.open("wb") as handle:
                handle.write(f"# {title}\n\n".encode("utf-8"))
                handle.write(processed)

            date = detect_date(content)
            with ESSAYS_CSV.open("a", encoding="utf-8", newline="") as handle:
                writer = csv.writer(
                    handle,
                    quoting=csv.QUOTE_MINIMAL,
                    delimiter=",",
                    quotechar='"',
                )
                writer.writerow([article_id, title, date, url])

            print(f"✅ {article_id} {title}")
        except Exception as exc:
            failures.append((article_id, title, str(exc)))
            print(f"❌ {article_id} {title} ({exc})")

        time.sleep(REQUEST_DELAY_SECONDS)

    if failures:
        details = "\n".join(
            f"  - {article_id} {title}: {error}"
            for article_id, title, error in failures
        )
        raise RuntimeError(
            f"Failed to download {len(failures)} selected essay(s):\n{details}"
        )

    summary = {
        "edition": selection.get("edition", "Selected Essays"),
        "source_index_count": len(all_entries),
        "included_count": article_no,
        "excluded_count": len(matched_exclusions),
        "configured_exclusion_count": len(excluded),
    }
    BUILD_SUMMARY.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        f"📚 Built source set for {article_no} selected essays; "
        f"{len(matched_exclusions)} explicitly excluded."
    )
    print(f"Edition: {selection.get('edition', 'Selected Essays')}")


if __name__ == "__main__":
    main()
