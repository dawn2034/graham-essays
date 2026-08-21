SHELL := /bin/bash

.PHONY: all clean bootstrap venv cover fetch validate merge epub pdf pdf-a5 pdf-b5 pdf-a4 volume-plan pdf-b5-volumes check check-volumes wordcount sample sample-check sample-clean
.SILENT: all clean bootstrap venv cover fetch validate merge epub pdf pdf-a5 pdf-b5 pdf-a4 volume-plan pdf-b5-volumes check check-volumes wordcount sample sample-check sample-clean

PYTHON ?= python3
VENV := .venv
VENV_PY := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip
PANDOC ?= pandoc
PDF_ENGINE ?= xelatex
MARKDOWN_FORMAT ?= markdown-tex_math_dollars

PDF_A5 := graham-a5.pdf
PDF_B5 := graham-b5.pdf
PDF_A4 := graham-a4.pdf
PDF_LEGACY := graham.pdf
PDF_B5_VOL1 := graham-b5-vol1.pdf
PDF_B5_VOL2 := graham-b5-vol2.pdf
PDF_B5_VOL3 := graham-b5-vol3.pdf
THEME_DIR := dist/theme-volumes

all: clean venv fetch validate merge epub pdf pdf-b5-volumes check check-volumes wordcount

clean:
	@echo "Cleaning generated files..."
	rm -rf essays dist cover.png graham.epub $(PDF_A5) $(PDF_B5) $(PDF_A4) $(PDF_LEGACY) \
		$(PDF_B5_VOL1) $(PDF_B5_VOL2) $(PDF_B5_VOL3) \
		graham.md essays.csv excluded_essays.csv build_summary.json

bootstrap:
	@echo "Installing system dependencies (Ubuntu/Debian only)..."
	@if command -v apt-get >/dev/null 2>&1; then \
		sudo apt-get update && sudo apt-get install -y \
			python3-pip python3-venv pandoc \
			texlive-xetex texlive-latex-extra texlive-fonts-recommended \
			fonts-noto-core fonts-dejavu-core poppler-utils unzip librsvg2-bin; \
	else \
		echo "Install Python 3, Pandoc, XeLaTeX, Noto fonts, Poppler, and unzip with your package manager."; \
	fi

venv:
	@echo "Creating Python environment..."
	@if [ ! -x "$(VENV_PY)" ]; then $(PYTHON) -m venv $(VENV); fi
	$(VENV_PY) -m pip install --disable-pip-version-check --upgrade pip setuptools wheel
	$(VENV_PIP) install --disable-pip-version-check -r requirements.txt

cover:
	@echo "Rendering the source cover..."
	@if command -v rsvg-convert >/dev/null 2>&1; then \
		rsvg-convert --width 2480 --height 3508 --output cover.png cover.svg; \
	elif command -v inkscape >/dev/null 2>&1; then \
		inkscape cover.svg --export-type=png --export-filename=cover.png \
			--export-width=2480 --export-height=3508 >/dev/null; \
	else \
		echo "Install librsvg (rsvg-convert) or Inkscape to render cover.svg." >&2; \
		exit 1; \
	fi

fetch: venv
	@echo "Downloading the selected essay set..."
	$(VENV_PY) graham.py

validate: venv
	@echo "Validating the selection boundary..."
	$(VENV_PY) scripts/validate_selection.py

merge:
	@echo "Merging articles..."
	$(PANDOC) essays/*.md -o graham.md -f $(MARKDOWN_FORMAT) --no-highlight

epub: merge cover
	@echo "Binding reflowable EPUB 3..."
	$(PANDOC) essays/*.md -o graham.epub -t epub3 -f $(MARKDOWN_FORMAT) --no-highlight \
		--metadata-file=metadata.yaml \
		--toc --toc-depth=1 \
		--epub-cover-image=cover.png \
		--css=epub.css
	$(PYTHON) scripts/fix_epub_ibooks.py graham.epub

pdf: pdf-a5 pdf-b5 pdf-a4
	@cp $(PDF_A5) $(PDF_LEGACY)
	@echo "Print PDFs created: A5, B5, A4 (graham.pdf remains an A5 compatibility copy)."

pdf-a5: merge cover
	@echo "Typesetting print-oriented A5 PDF..."
	$(PANDOC) essays/*.md -o $(PDF_A5) -f $(MARKDOWN_FORMAT) --no-highlight \
		--metadata-file=metadata.yaml --metadata-file=print-metadata-a5.yaml \
		--toc --toc-depth=1 --top-level-division=chapter \
		--pdf-engine=$(PDF_ENGINE) \
		--include-in-header=print-header.tex --include-in-header=print-cover.tex

pdf-b5: merge cover
	@echo "Typesetting print-oriented B5 PDF..."
	$(PANDOC) essays/*.md -o $(PDF_B5) -f $(MARKDOWN_FORMAT) --no-highlight \
		--metadata-file=metadata.yaml --metadata-file=print-metadata-b5.yaml \
		--toc --toc-depth=1 --top-level-division=chapter \
		--pdf-engine=$(PDF_ENGINE) \
		--include-in-header=print-header.tex --include-in-header=print-cover.tex

pdf-a4: merge cover
	@echo "Typesetting print-oriented A4 PDF..."
	$(PANDOC) essays/*.md -o $(PDF_A4) -f $(MARKDOWN_FORMAT) --no-highlight \
		--metadata-file=metadata.yaml --metadata-file=print-metadata-a4.yaml \
		--toc --toc-depth=1 --top-level-division=chapter \
		--pdf-engine=$(PDF_ENGINE) \
		--include-in-header=print-header.tex --include-in-header=print-cover.tex

volume-plan: validate
	@echo "Preparing theme-oriented B5 three-volume plan..."
	$(VENV_PY) scripts/build_theme_volumes.py

pdf-b5-volumes: volume-plan
	@echo "Typesetting B5 Volume I — Thinking & Making..."
	$(PANDOC) $(THEME_DIR)/vol1.md -o $(PDF_B5_VOL1) -f $(MARKDOWN_FORMAT) --no-highlight \
		--metadata-file=metadata.yaml --metadata-file=print-metadata-b5.yaml --metadata-file=$(THEME_DIR)/vol1-metadata.yaml \
		--toc --toc-depth=1 --top-level-division=chapter --pdf-engine=$(PDF_ENGINE) \
		--include-in-header=print-header.tex --include-in-header=$(THEME_DIR)/vol1-cover.tex
	@echo "Typesetting B5 Volume II — Work & Startups..."
	$(PANDOC) $(THEME_DIR)/vol2.md -o $(PDF_B5_VOL2) -f $(MARKDOWN_FORMAT) --no-highlight \
		--metadata-file=metadata.yaml --metadata-file=print-metadata-b5.yaml --metadata-file=$(THEME_DIR)/vol2-metadata.yaml \
		--toc --toc-depth=1 --top-level-division=chapter --pdf-engine=$(PDF_ENGINE) \
		--include-in-header=print-header.tex --include-in-header=$(THEME_DIR)/vol2-cover.tex
	@echo "Typesetting B5 Volume III — Life & Judgment..."
	$(PANDOC) $(THEME_DIR)/vol3.md -o $(PDF_B5_VOL3) -f $(MARKDOWN_FORMAT) --no-highlight \
		--metadata-file=metadata.yaml --metadata-file=print-metadata-b5.yaml --metadata-file=$(THEME_DIR)/vol3-metadata.yaml \
		--toc --toc-depth=1 --top-level-division=chapter --pdf-engine=$(PDF_ENGINE) \
		--include-in-header=print-header.tex --include-in-header=$(THEME_DIR)/vol3-cover.tex

check: venv
	@echo "Running structural and typography checks..."
	$(VENV_PY) scripts/check_outputs.py \
		--epub graham.epub \
		--pdf-a5 $(PDF_A5) --pdf-b5 $(PDF_B5) --pdf-a4 $(PDF_A4) \
		--included essays.csv --excluded excluded_essays.csv \
		--manifest selection.json

check-volumes: pdf-b5-volumes
	@echo "Validating themed B5 volume set..."
	$(VENV_PY) scripts/check_theme_volumes.py \
		--included essays.csv \
		--plan $(THEME_DIR)/theme-volume-plan.json \
		--vol1 $(PDF_B5_VOL1) --vol2 $(PDF_B5_VOL2) --vol3 $(PDF_B5_VOL3) \
		--summary-out $(THEME_DIR)/theme-volume-summary.json

wordcount:
	@echo "Collection statistics"
	@printf "Total words: "; cat essays/*.md | wc -w
	@printf "Included articles: "; find essays -maxdepth 1 -name '*.md' | wc -l
	@printf "Excluded articles: "; tail -n +2 excluded_essays.csv | wc -l

sample: sample-clean cover
	@echo "Building copyright-safe typography proofs..."
	mkdir -p dist/sample
	$(PANDOC) sample/*.md -o dist/sample/layout-proof.epub -t epub3 -f $(MARKDOWN_FORMAT) --no-highlight \
		--metadata-file=sample/metadata.yaml --toc --toc-depth=1 \
		--epub-cover-image=cover.png --css=epub.css
	$(PYTHON) scripts/fix_epub_ibooks.py dist/sample/layout-proof.epub
	$(PANDOC) sample/*.md -o dist/sample/layout-proof-a5.pdf -f $(MARKDOWN_FORMAT) --no-highlight \
		--metadata-file=sample/metadata.yaml --metadata-file=print-metadata-a5.yaml \
		--toc --toc-depth=1 --top-level-division=chapter --pdf-engine=$(PDF_ENGINE) \
		--include-in-header=print-header.tex --include-in-header=print-cover.tex
	$(PANDOC) sample/*.md -o dist/sample/layout-proof-b5.pdf -f $(MARKDOWN_FORMAT) --no-highlight \
		--metadata-file=sample/metadata.yaml --metadata-file=print-metadata-b5.yaml \
		--toc --toc-depth=1 --top-level-division=chapter --pdf-engine=$(PDF_ENGINE) \
		--include-in-header=print-header.tex --include-in-header=print-cover.tex
	$(PANDOC) sample/*.md -o dist/sample/layout-proof-a4.pdf -f $(MARKDOWN_FORMAT) --no-highlight \
		--metadata-file=sample/metadata.yaml --metadata-file=print-metadata-a4.yaml \
		--toc --toc-depth=1 --top-level-division=chapter --pdf-engine=$(PDF_ENGINE) \
		--include-in-header=print-header.tex --include-in-header=print-cover.tex
	$(PYTHON) scripts/check_layout_proof.py

sample-check:
	$(PYTHON) scripts/check_layout_proof.py

sample-clean:
	rm -rf dist/sample
