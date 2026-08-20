# Paul Graham Essays - Selected Reader's Edition

This fork builds a deliberately selected edition of Paul Graham's essays in two formats:

- a reflowable EPUB3 for e-readers;
- an A5, duplex-aware PDF typeset directly from Markdown for paper reading.

The canonical source remains [Paul Graham's essay index](https://paulgraham.com/articles.html). Selection is controlled by [`selection.json`](selection.json). The 29 configured titles are omitted; every other title is included, and newly published essays are included by default.

## Current selection baseline

At the 2026-06-15 source baseline:

- 233 essays on the official index;
- 29 configured exclusions;
- 204 essays in this edition.

The scraper verifies every configured exclusion against the live index and fails if any title no longer matches. It also fails if any included essay cannot be downloaded, so a successful build cannot silently ship a partial book.

## Build

System dependencies on Debian/Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y \
  python3-venv pandoc texlive-xetex texlive-latex-extra \
  fonts-noto-core fonts-dejavu-core poppler-utils
```

Then run:

```bash
make all
```

Outputs are staged in `dist/`:

- `paul-graham-selected-essays.epub`
- `paul-graham-selected-essays.pdf`
- `essays.csv`
- `excluded_essays.csv`
- `edition-summary.json`
- `build-validation.json`

## Typography

### EPUB

The EPUB is reflowable and uses relative sizing. It requests a book-serif stack (`Literata`, `Charis SIL`, `Noto Serif`, `Georgia`) without embedding or forcing a font, and it avoids fixed text/background colors so Apple Books, Kindle and other readers can apply their own themes. Paragraph spacing and a 1.55 line-height are tuned for screen reading.

### PDF

The PDF is built directly with XeLaTeX rather than converted from EPUB:

- ISO A5, mirrored margins for duplex printing;
- Noto Serif, 11 pt body text;
- 22 mm inner and 17 mm outer margins;
- restrained 1.16 line spacing and traditional paragraph indentation;
- essay title on odd-page running heads, author on even pages;
- page numbers at the outside edge;
- one essay begins on a fresh page, without forcing blank recto pages;
- monochrome links and embedded/subset fonts.

## Validation

`make validate` checks:

- the live source count, inclusion count and all 29 exclusions;
- EPUB ZIP invariants, metadata and table of contents;
- absence of excluded titles from EPUB navigation;
- A5 PDF page size, bookmarks, and embedded fonts;
- presence of every included essay in EPUB navigation and PDF bookmarks.

The build intentionally disables Pandoc's dollar-delimited math parser, because ordinary currency expressions in essays must remain text rather than accidental TeX.

## Rights

The essays remain copyright Paul Graham. This repository provides build tooling for a personal reader's edition and is not an official publication.
