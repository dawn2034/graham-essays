# Paul Graham: Selected Essays

This repository builds a deliberately narrow **selected reading edition** from
Paul Graham's current essay index. It excludes exactly the 29 titles classified
as safe to skip in the accompanying reading guide. The auditable boundary lives
in [`selection.json`](selection.json); essays that were merely lower priority
remain included.

At the 2026-06-15 baseline, the source index contained 233 items. The declared
policy therefore yielded 204 included items. Later essays are included by
default unless they are intentionally added to the exclusion manifest.

## Outputs

A live local build produces:

- `graham.epub` - reflowable EPUB 3 for Apple Books and other readers;
- `graham-a5.pdf` - compact duplex print edition;
- `graham-b5.pdf` - ISO B5 duplex print edition;
- `graham-a4.pdf` - A4 duplex print edition;
- `graham.pdf` - compatibility copy of the A5 edition;
- `graham.md` - merged Markdown source;
- `essays.csv` - included essays in reading order;
- `excluded_essays.csv` - exclusion audit with title, category, URL, and status;
- `build_summary.json` - source, inclusion, and exclusion counts.

The reading order is obtained by reversing the official source index, following
the upstream project. It is broadly old-to-new but is **not guaranteed to be a
strict chronological bibliography**, because the index also contains undated
book chapters and other material.

## Typography

### EPUB

The EPUB keeps its base size adjustable and uses a serif fallback stack
(Literata, Charis SIL, Noto Serif, Georgia), 1.55 line spacing, modest first-line
indents, restrained headings, and no fixed foreground/background colors. Fonts
are not embedded, allowing reader themes and accessibility controls to work.
The Apple Books display-options file is patched so dark mode does not produce
invisible text.

### Print PDFs

All PDFs are typeset directly from Markdown through XeLaTeX rather than
converted from EPUB. They share Noto Serif body text, microtypography, outside
page numbers, restrained running heads, real page footnotes, widow/orphan
control, robust URL and code wrapping, and one essay per new page.

- **A5:** 11 pt body; 22 mm inner / 17 mm outer margins; 18 mm top / 20 mm bottom.
- **ISO B5:** 11 pt body; 24 mm inner / 20 mm outer margins; 21 mm top / 23 mm bottom.
- **A4:** 12 pt body; 30 mm inner / 25 mm outer margins; 25 mm top / 28 mm bottom.

The cover is stored as editable SVG source and rendered to a high-resolution
PNG during the build. It has nearly the same aspect ratio as A-series and ISO
B5 paper, so it scales to each page size without material distortion. `openany` is
intentional: forcing every one of 200+ essays onto a right-hand page would add a
large number of blank pages without improving readability.

## Build

Install OS dependencies once on Ubuntu/Debian:

```bash
make bootstrap
```

Then build and validate the current selected edition:

```bash
make
```

The live build needs network access to `paulgraham.com`. Individual targets:

```bash
make venv
make fetch
make validate
make epub
make pdf-a5
make pdf-b5
make pdf-a4
make check
```

For offline, copyright-safe typography proofs containing only synthetic text:

```bash
make sample
```

This creates and validates one EPUB plus A5, ISO B5, and A4 PDF proofs under
`dist/sample/`.

## Selection and output guarantees

- Title matching is Unicode-, whitespace-, apostrophe-, and case-normalized.
- Source files are cleared before every fetch, preventing stale essays from
  surviving a changed selection.
- The build fails if any configured exclusion is absent from the current index,
  leaks into the included CSV, or appears in EPUB/PDF navigation.
- Article numbering is regenerated after filtering and must remain contiguous.
- EPUB validation checks its uncompressed mimetype, package metadata, Apple
  Books font override, and one navigation entry per included essay.
- PDF validation checks metadata, every page's declared paper size, embedded and
  subset fonts, valid outlines, and one outline entry per included essay.

## Continuous integration and releases

GitHub Actions builds the live edition and all three print sizes, validates the
outputs, builds synthetic typography proofs, uploads the complete build as a
workflow artifact, and publishes a GitHub Release on every source-changing push
to `main`. Each release contains the EPUB, A5/B5/A4 PDFs, selection and audit
metadata, the live build summary, and SHA-256 checksums.

Scheduled and pull-request runs validate the same pipeline but do not publish a
release.

## Rights

Essay copyrights remain with Paul Graham. This repository provides selection,
retrieval, and typesetting code; it does not grant rights in the essay text. The
included cover is an original typographic design for this reading edition.
