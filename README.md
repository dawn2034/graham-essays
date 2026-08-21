# Paul Graham: Selected Essays

This repository builds a deliberately narrow **selected reading edition** from Paul Graham's current essay index. It excludes exactly the 29 titles classified as safe to skip in the accompanying reading guide. The auditable exclusion boundary lives in [`selection.json`](selection.json); essays that were merely lower priority remain included.

At the 2026-06-15 baseline, the source index contained 233 items. The declared policy therefore yielded 204 included items. Later essays are included by default unless they are intentionally added to the exclusion manifest.

## Outputs

A live build produces:

- `graham.epub` — reflowable EPUB 3;
- `graham-a5.pdf` — A5 duplex print edition;
- `graham-b5.pdf` — single-volume ISO B5 edition;
- `graham-a4.pdf` — A4 duplex print edition;
- `graham-b5-vol1.pdf` — **Volume I: Thinking & Making**;
- `graham-b5-vol2.pdf` — **Volume II: Work & Startups**;
- `graham-b5-vol3.pdf` — **Volume III: Life & Judgment**;
- `essays.csv`, `excluded_essays.csv`, `build_summary.json` — build audit files;
- `dist/theme-volumes/theme-volume-plan.json` — per-essay theme allocation and classifier scores;
- `dist/theme-volumes/theme-volume-summary.json` — validated page counts and volume ranges.

## Themed B5 three-volume edition

The physical-reading edition is organized by editorial theme rather than by equal page counts:

### Volume I — Thinking & Making

Learning, independent thought, new ideas, writing, programming, taste, design, creativity, expertise, and the craft of making things.

### Volume II — Work & Startups

Careers, projects, work habits, startup ideas, products, users, founders, growth, management, hiring, and company building.

### Volume III — Life & Judgment

Time, identity, education, cities, family, wealth, culture, society, values, judgment, and reflective autobiographical writing.

Important essays are assigned explicitly in [`theme-volumes.json`](theme-volumes.json). Other essays are classified from their title and full text using auditable weighted theme vocabularies, so newly published essays can still be placed automatically. Theme grouping changes cross-volume order, but each volume preserves the original relative reading order of its essays.

Each volume has its own generated front-cover artwork at repository root: `vol_1.png`, `vol_2.png`, and `vol_3.png`. The artwork is inserted as page 1 of the corresponding PDF and is also published as a separate Release asset for printing workflows.

## Print typography

All print PDFs are typeset directly from Markdown through XeLaTeX rather than converted from EPUB. They use Noto Serif body text, microtypography, outside page numbers, restrained running heads, real page footnotes, widow/orphan control, robust URL/code wrapping, and one essay per new page.

- **A5:** 11 pt; 22 mm inner / 17 mm outer; 18 mm top / 20 mm bottom.
- **ISO B5:** 11 pt; 24 mm inner / 20 mm outer; 21 mm top / 23 mm bottom.
- **A4:** 12 pt; 30 mm inner / 25 mm outer; 25 mm top / 28 mm bottom.
- **B5 themed volumes:** the same B5 typography and margins, with independent covers, contents, page numbering, running heads, and bookmarks.

For a physical copy, high-opacity off-white book/offset paper around 70 g/m² is a sensible starting point. Sewn binding is preferable; PUR perfect binding is also practical at three-volume thicknesses.

## Build

On Ubuntu/Debian, install dependencies once:

```bash
make bootstrap
```

Then build and validate everything:

```bash
make
```

Useful individual targets:

```bash
make fetch
make validate
make epub
make pdf-a5
make pdf-b5
make pdf-a4
make volume-plan
make pdf-b5-volumes
make check
make check-volumes
```

The live build needs network access to `paulgraham.com`.

For copyright-safe typography proofs containing only synthetic text:

```bash
make sample
```

## Validation guarantees

- The 29-title exclusion boundary is checked against the live source index.
- Excluded titles cannot leak into the selected CSV, EPUB navigation, or single-volume PDF outlines.
- Article numbering is regenerated after filtering and must remain contiguous.
- EPUB structure, metadata, Apple Books settings, and navigation are checked.
- A5/B5/A4 page sizes, embedded/subset fonts, metadata, and outlines are checked.
- The themed B5 validator checks ISO B5 sizing, font embedding, first-page cover artwork, per-volume outlines, exact all-essay coverage with no duplicates/omissions, and preservation of original relative order inside every volume.

## Releases

On every source-changing push to `main`, GitHub Actions builds and validates the full selected edition and publishes a Release containing:

- EPUB;
- A5/B5/A4 single-volume PDFs;
- themed B5 Volumes I–III;
- the three themed cover PNGs;
- selection, classification, build, and checksum metadata.

## Rights

Essay copyrights remain with Paul Graham. This repository provides selection, retrieval, and typesetting code; it does not grant rights in the essay text. The cover artwork was created specifically for this private-reading edition.
