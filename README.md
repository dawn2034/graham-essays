# Paul Graham: Selected Essays

This fork builds a deliberately narrow **selected reading edition** from Paul
Graham's current essay index. It excludes exactly the 29 titles explicitly
classified as safe to skip in the accompanying reading guide. The auditable
boundary lives in [`selection.json`](selection.json); lower-priority essays are
otherwise retained.

At the 2026-06-15 upstream baseline, the complete index contains 233 items, so
this policy produces 204 included items. Later essays are included by default
unless they are intentionally added to the exclusion manifest.

## Outputs

A live build produces:

- `graham.epub` - reflowable EPUB 3 for Apple Books and other readers.
- `graham.pdf` - A5, duplex-aware PDF intended for paper reading.
- `graham.md` - merged Markdown source.
- `essays.csv` - included essays in chronological order.
- `excluded_essays.csv` - exclusion audit with title, category, URL, and status.

GitHub Actions stages the validated deliverables and inspection reports under
`dist/live/` and uploads them as `paul-graham-selected-edition`.

## Typography

### EPUB

The EPUB keeps the base size adjustable and uses a serif fallback stack
(Literata, Charis SIL, Noto Serif, Georgia), 1.55 line spacing, modest first-line
indents, restrained headings, and no fixed foreground/background colors. Fonts
are not embedded, allowing device themes and accessibility controls to work.
The Apple Books display-options file is patched so dark mode does not produce
invisible text.

### PDF

The PDF is typeset directly from Markdown through XeLaTeX rather than converted
from EPUB. Its print settings are:

- A5 paper, two-sided layout, chapters allowed to start on either side.
- Noto Serif 11 pt body, microtypography, and moderate leading.
- 22 mm inner / 17 mm outer margins, with 18 mm top / 20 mm bottom margins.
- Outside page numbers, restrained running heads, real page footnotes.
- Widow/orphan control, robust URL/code wrapping, and one essay per new page.

## Build

Install OS dependencies once on Ubuntu/Debian:

```bash
make bootstrap
```

Then build the live edition:

```bash
make
```

The live build needs network access to `paulgraham.com`. Individual targets:

```bash
make venv
make fetch
make validate
make epub
make pdf
make check
```

## Selection guarantees

- Title matching is Unicode-, whitespace-, apostrophe-, and case-normalized.
- Source files are cleared before every fetch, preventing stale essays from
  surviving a changed selection.
- The build fails if any of the 29 configured exclusions is absent from the
  downloaded index or leaks into the included table of contents.
- Article numbering is regenerated after filtering and must remain contiguous.

## Rights

Essay copyrights remain with Paul Graham. The repository provides selection,
retrieval, and typesetting code; it does not grant rights in the essay text.
The build retains the repository's existing cover asset; its separate rights
notice remains in the project history and upstream source.
