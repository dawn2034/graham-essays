## Repository instructions

This is a Python CLI and document-build project. It scrapes Paul Graham's public
essay index, removes the exact titles listed in `selection.json`, and builds an
EPUB plus A5, ISO B5, and A4 print PDFs. There is no web server or database.

### System dependencies

- Python 3 and `venv`
- Pandoc
- XeLaTeX / TeX Live (`texlive-xetex`, `texlive-latex-extra`)
- Noto Serif, Noto Sans, and DejaVu Sans Mono system fonts
- Poppler utilities (`pdfinfo`, `pdffonts`, `pdftotext`)
- librsvg (`rsvg-convert`) or Inkscape for rendering `cover.svg`
- GNU Make and unzip

On Ubuntu/Debian, `make bootstrap` installs the OS dependencies.

### Build pipeline

```bash
make venv       # create .venv and install Python dependencies
make cover      # render cover.svg to the generated cover.png
make fetch      # download the selected live essay set
make validate   # verify all exclusions matched and no title leaked
make merge      # create graham.md
make epub       # create graham.epub
make pdf-a5     # create graham-a5.pdf
make pdf-b5     # create graham-b5.pdf
make pdf-a4     # create graham-a4.pdf
make check      # validate EPUB and all three PDFs
```

`make all` (or simply `make`) performs the complete live build. `make sample`
builds synthetic, copyright-safe layout proofs without downloading essays.

### Important invariants

- Do not silently broaden or narrow the selection. `selection.json` is the
  auditable policy boundary and currently contains exactly 29 exclusions.
- `graham.py` must clear stale generated essay files before fetching.
- Footnote identifiers must remain globally unique across the anthology.
- EPUB text and background colors must remain reader-controlled; Apple Books
  `specified-fonts=false` support is required.
- The PDF source format is `markdown-tex_math_dollars`; dollar amounts must not
  be parsed as TeX math.
- PDF output is generated directly with XeLaTeX. Do not replace it with an
  EPUB-to-PDF conversion.
- A5, ISO B5, and A4 page dimensions, embedded/subset fonts, outlines, and title
  leakage are checked by `scripts/check_outputs.py`.
- `graham.pdf` is only a compatibility copy of `graham-a5.pdf`; release assets
  use explicit paper-size names.

### GitHub Actions

The workflow builds and validates the live edition, creates synthetic proofs,
and publishes a release only for source-changing pushes to `main`. Pull-request
and scheduled runs validate but do not release. Release assets include EPUB,
A5/B5/A4 PDFs, CSV audits, build summary, selection manifest, and checksums.
