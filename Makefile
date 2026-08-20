SHELL := /bin/bash
.ONESHELL:
.NOTPARALLEL:

PYTHON ?= python3
PANDOC ?= pandoc
PDF_ENGINE ?= xelatex
VENV := .venv
VENV_PYTHON := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip
LIVE_REPORTS := build-reports/live

.PHONY: all bootstrap clean distclean venv fetch validate merge epub pdf check \
        wordcount stage

all: clean venv fetch validate merge epub pdf check wordcount

bootstrap:
	if command -v apt-get >/dev/null 2>&1; then
		sudo apt-get update
		sudo apt-get install -y \
			python3-pip python3-venv pandoc \
			texlive-xetex texlive-latex-extra texlive-fonts-recommended \
			fonts-noto-core fonts-dejavu-core poppler-utils unzip
	else
		echo "bootstrap currently supports Debian/Ubuntu; install equivalent packages manually." >&2
		exit 1
	fi

clean:
	rm -rf essays essays.selected.tmp
	rm -f essays.csv essays.selected.csv.tmp excluded_essays.csv build_summary.json
	rm -f graham.md graham.epub graham.pdf fetch.log
	rm -rf $(LIVE_REPORTS) dist/live

# Remove dependencies and all staged artifacts as well.
distclean: clean
	rm -rf $(VENV) dist build-reports

venv:
	if [ ! -x "$(VENV_PYTHON)" ]; then
		$(PYTHON) -m venv $(VENV)
	fi
	$(VENV_PYTHON) -m pip install --upgrade pip setuptools wheel
	$(VENV_PIP) install -r requirements.txt

fetch: venv
	rm -rf essays essays.csv excluded_essays.csv build_summary.json fetch.log
	mkdir -p essays
	set -o pipefail
	$(VENV_PYTHON) graham.py 2>&1 | tee fetch.log
	if grep -Fq '❌' fetch.log; then
		echo "The upstream scraper reported one or more failed downloads." >&2
		exit 1
	fi
	$(VENV_PYTHON) scripts/apply_selection.py

validate:
	$(VENV_PYTHON) scripts/validate_selection.py

merge: validate
	cat essays/*.md > graham.md

epub: validate metadata.yaml epub.css cover.png
	$(PANDOC) essays/*.md \
		--output=graham.epub \
		--from=markdown+smart \
		--to=epub3 \
		--metadata-file=metadata.yaml \
		--toc --toc-depth=1 \
		--split-level=1 \
		--epub-cover-image=cover.png \
		--css=epub.css
	$(PYTHON) scripts/fix_epub_ibooks.py graham.epub

pdf: validate metadata.yaml print-metadata.yaml print-header.tex
	$(PANDOC) essays/*.md \
		--output=graham.pdf \
		--from=markdown+smart \
		--metadata-file=metadata.yaml \
		--metadata-file=print-metadata.yaml \
		--toc --toc-depth=1 \
		--pdf-engine=$(PDF_ENGINE) \
		--include-in-header=print-header.tex \
		--no-highlight

check: epub pdf
	$(VENV_PYTHON) scripts/check_outputs.py \
		--epub graham.epub \
		--pdf graham.pdf \
		--title 'Paul Graham: Selected Essays' \
		--author 'Paul Graham' \
		--essays-csv essays.csv \
		--selection selection.json \
		--audit excluded_essays.csv \
		--summary build_summary.json \
		--report-dir $(LIVE_REPORTS)

wordcount: validate
	echo "Total words: $$(cat essays/*.md | wc -w)"
	echo "Included articles: $$(find essays -maxdepth 1 -name '*.md' | wc -l)"
	echo -n "Excluded articles: "
	$(VENV_PYTHON) -c 'import json; print(len(json.load(open("selection.json", encoding="utf-8"))["excluded"]))'

stage:
	for file in graham.epub graham.pdf graham.md essays.csv excluded_essays.csv \
		selection.json build_summary.json; do
		test -f "$$file" || { echo "Missing validated build output: $$file" >&2; exit 1; }
	done
	test -f "$(LIVE_REPORTS)/validation.json" || { \
		echo "Missing validation report: $(LIVE_REPORTS)/validation.json" >&2; exit 1; \
	}
	rm -rf dist/live
	mkdir -p dist/live
	cp graham.epub graham.pdf graham.md essays.csv excluded_essays.csv \
		selection.json build_summary.json dist/live/
	cp -a $(LIVE_REPORTS) dist/live/validation
