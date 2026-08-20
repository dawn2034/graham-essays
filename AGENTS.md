## Repository workflow

This is a Python CLI pipeline that downloads a deliberately selected subset of
Paul Graham's essay index and builds two reading editions:

- a reflowable EPUB 3;
- a print-oriented A5 PDF typeset with XeLaTeX.

There is no web server or database. The selection boundary is declared in
`selection.json` and audited in `excluded_essays.csv`.

### System dependencies

- Python 3
- Python virtual environments (`python3-venv`)
- Pandoc
- XeLaTeX with `microtype`, `fancyhdr`, `titlesec`, `tocloft`, `xurl`, and
  `fvextra`
- Noto Serif, Noto Sans, and DejaVu Sans Mono
- Poppler (`pdfinfo`, `pdffonts`)
- GNU Make and unzip

### Full build

```bash
make all
```

The pipeline performs these stages:

```bash
make clean
make venv
make fetch
make validate
make merge
make epub
make pdf
make check
```

`make fetch` requires access to `paulgraham.com`. It runs the upstream complete
collection scraper, fails if the scraper logs any download error, and then
applies `selection.json` through `scripts/apply_selection.py`. The filter
rebuilds the article directory and CSV with contiguous numbering.

### Selection invariants

- Only titles in `selection.json` are excluded.
- Title matching is Unicode-, apostrophe-, whitespace-, and case-normalized.
- Every configured exclusion must still be present on the live index.
- Excluded and included title sets must not overlap.
- Included numbering and Markdown files must be contiguous and complete.

### Output invariants

`scripts/check_outputs.py` verifies that:

- the EPUB has a valid uncompressed mimetype entry;
- Apple Books may override fonts and themes;
- EPUB metadata has one Paul Graham creator and one chapter per included essay;
- the PDF is A5 and has the intended title/author metadata;
- every PDF font is embedded and subset.

The GitHub Actions workflow uploads EPUB, PDF, Markdown, selection/audit CSVs,
the build summary, and PDF inspection reports as the
`paul-graham-selected-edition` artifact.

### PDF typography

The PDF uses Noto Serif at 11 pt, asymmetric binding margins, truncated running heads,
outside page numbers, compact contents pages, real page footnotes, and
widow/orphan control. Syntax highlighting is disabled for a quiet monochrome
page; long code lines are wrapped with `fvextra`.

### EPUB typography

The EPUB does not embed or force fonts. Its CSS provides a serif fallback stack,
relative sizing, first-line indents, restrained headings, and no fixed text or
background colors, preserving reader accessibility settings and Apple Books
dark mode.
