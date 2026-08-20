SHELL := /bin/bash

PYTHON ?= .venv/bin/python
PANDOC ?= pandoc
OUTPUT_STEM := paul-graham-selected-essays
EPUB := $(OUTPUT_STEM).epub
PDF := $(OUTPUT_STEM).pdf
MARKDOWN_READER := markdown+footnotes+smart-tex_math_dollars

.PHONY: all clean venv fetch merge epub pdf validate stage wordcount

all: clean venv fetch merge epub pdf validate stage wordcount

clean:
	@echo "Cleaning generated files..."
	rm -rf essays .venv dist graham.md $(EPUB) $(PDF) essays.csv excluded_essays.csv edition-summary.json build-validation.json

venv:
	@echo "Creating Python environment..."
	python3 -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

fetch:
	@echo "Downloading and filtering essays..."
	$(PYTHON) graham.py

merge:
	@echo "Merging selected Markdown..."
	test -n "$$(find essays -maxdepth 1 -name '*.md' -print -quit)"
	$(PANDOC) essays/*.md -o graham.md -f '$(MARKDOWN_READER)' -t gfm --wrap=none

epub: merge
	@echo "Building reflowable EPUB3..."
	$(PANDOC) essays/*.md -o $(EPUB) \
		-f '$(MARKDOWN_READER)' -t epub3 \
		--metadata-file=metadata.yaml --toc --toc-depth=1 \
		--split-level=1 --epub-cover-image=cover.png --css=epub.css
	$(PYTHON) scripts/fix_epub_ibooks.py $(EPUB)

pdf: merge
	@echo "Building A5 duplex print PDF..."
	$(PANDOC) essays/*.md -o $(PDF) \
		-f '$(MARKDOWN_READER)' --pdf-engine=xelatex \
		--metadata-file=metadata.yaml --toc --toc-depth=1 \
		--top-level-division=chapter --include-in-header=print-header.tex \
		--listings \
		-V documentclass=book -V classoption=openany -V classoption=twoside \
		-V fontsize=11pt -V papersize=a5 -V colorlinks=false

validate: epub pdf
	@echo "Validating selection and book files..."
	$(PYTHON) scripts/validate_outputs.py

ebook: epub pdf

stage: validate
	mkdir -p dist
	cp $(EPUB) $(PDF) essays.csv excluded_essays.csv edition-summary.json build-validation.json dist/

wordcount:
	@printf "Selected essays: "; find essays -maxdepth 1 -name '*.md' | wc -l
	@printf "Words: "; cat essays/*.md | wc -w
