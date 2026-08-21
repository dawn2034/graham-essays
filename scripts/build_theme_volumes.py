#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ESSAYS_DIR = ROOT / "essays"
INCLUDED_CSV = ROOT / "essays.csv"
CONFIG_PATH = ROOT / "theme-volumes.json"
OUT_DIR = ROOT / "dist" / "theme-volumes"


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


def term_count(text: str, term: str) -> int:
    term = normalize(term)
    if " " in term:
        return text.count(term)
    return len(re.findall(rf"(?<![\w]){re.escape(term)}(?![\w])", text))


def classify(title: str, body: str, config: dict) -> tuple[str, dict[str, int], str]:
    manual = {
        canonical_title(key): value
        for key, value in config.get("manual_assignments", {}).items()
    }
    title_key = canonical_title(title)
    if title_key in manual:
        slug = manual[title_key]
        return slug, {slug: 10_000}, "manual"

    # The title is repeated to make it substantially more important than casual
    # mentions in a long essay, while still allowing the essay body to disambiguate
    # vague titles such as "The Other Road Ahead".
    corpus = normalize((title + " ") * 12 + body)
    scores: dict[str, int] = {}
    for slug, weights in config.get("keyword_weights", {}).items():
        score = 0
        for term, weight in weights.items():
            score += term_count(corpus, term) * int(weight)
        scores[slug] = score

    # Volume I is the neutral/default home for essays about making and thought.
    # Ties therefore resolve to vol1; explicit manuals above handle important
    # exceptions where the theme is editorial rather than lexical.
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0] != "vol1", item[0]))
    slug = ordered[0][0] if ordered and ordered[0][1] > 0 else "vol1"
    return slug, scores, "keyword"


def markdown_files_by_number() -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in sorted(ESSAYS_DIR.glob("*.md")):
        match = re.match(r"^(\d+)_", path.name)
        if not match:
            continue
        result[match.group(1).zfill(3)] = path
    return result


def write_cover_tex(path: Path, image_path: Path) -> None:
    image_rel = image_path.relative_to(ROOT).as_posix()
    tex = rf"""% Auto-generated themed volume cover.
\usepackage{{graphicx}}
\usepackage{{eso-pic}}

\makeatletter
\renewcommand{{\maketitle}}{{%
  \begin{{titlepage}}%
    \thispagestyle{{empty}}%
    \AddToShipoutPictureBG*{{%
      \AtPageLowerLeft{{%
        \includegraphics[width=\paperwidth,height=\paperheight]{{{image_rel}}}%
      }}%
    }}%
    \null%
  \end{{titlepage}}%
}}
\makeatother
"""
    path.write_text(tex, encoding="utf-8")


def write_metadata(path: Path, label: str, subtitle: str) -> None:
    path.write_text(
        "---\n"
        f'title: "Paul Graham: Selected Essays — {label}: {subtitle}"\n'
        'author: "Paul Graham"\n'
        "...\n",
        encoding="utf-8",
    )


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    with INCLUDED_CSV.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    files = markdown_files_by_number()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    essays: list[dict] = []
    for row in rows:
        article_no = row["Article no."].strip().zfill(3)
        path = files.get(article_no)
        if path is None:
            raise RuntimeError(f"Missing markdown source for article {article_no}: {row['Title']}")
        body = path.read_text(encoding="utf-8")
        slug, scores, reason = classify(row["Title"], body, config)
        essays.append(
            {
                "article_no": article_no,
                "title": row["Title"],
                "slug": slug,
                "path": path,
                "scores": scores,
                "reason": reason,
            }
        )

    planned: list[dict] = []
    for volume in config["volumes"]:
        slug = volume["slug"]
        selected = [essay for essay in essays if essay["slug"] == slug]
        if not selected:
            raise RuntimeError(f"No essays assigned to {slug}")

        md_path = OUT_DIR / f"{slug}.md"
        md_path.write_text(
            "\n\n".join(item["path"].read_text(encoding="utf-8") for item in selected)
            + "\n",
            encoding="utf-8",
        )

        cover = ROOT / volume["cover_file"]
        if not cover.is_file():
            raise RuntimeError(f"Missing cover image: {cover}")
        cover_tex = OUT_DIR / f"{slug}-cover.tex"
        metadata = OUT_DIR / f"{slug}-metadata.yaml"
        write_cover_tex(cover_tex, cover)
        write_metadata(metadata, volume["label"], volume["subtitle"])

        planned.append(
            {
                "slug": slug,
                "label": volume["label"],
                "subtitle": volume["subtitle"],
                "essay_count": len(selected),
                "first_title": selected[0]["title"],
                "last_title": selected[-1]["title"],
                "titles": [item["title"] for item in selected],
                "article_numbers": [item["article_no"] for item in selected],
                "classifications": [
                    {
                        "title": item["title"],
                        "article_no": item["article_no"],
                        "reason": item["reason"],
                        "scores": item["scores"],
                    }
                    for item in selected
                ],
                "markdown": md_path.relative_to(ROOT).as_posix(),
                "cover": cover.relative_to(ROOT).as_posix(),
                "cover_tex": cover_tex.relative_to(ROOT).as_posix(),
                "metadata": metadata.relative_to(ROOT).as_posix(),
            }
        )

    plan = {
        "edition": config["edition"],
        "strategy": config["strategy"],
        "volume_count": len(planned),
        "included_essay_count": len(rows),
        "volumes": planned,
    }
    (OUT_DIR / "theme-volume-plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    counts = ", ".join(
        f"{item['label']}={item['essay_count']}" for item in planned
    )
    print(f"Theme volume plan created: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
