#!/usr/bin/env bash
# Requires TeX Live; include BibTeX and enough passes to resolve references.
set -euo pipefail
cd "$(dirname "$0")/../report"
for report_name in main extended; do
  pdflatex -interaction=nonstopmode -halt-on-error "$report_name" > "$report_name.build.log"
  bibtex "$report_name" >> "$report_name.build.log"
  pdflatex -interaction=nonstopmode -halt-on-error "$report_name" >> "$report_name.build.log"
  pdflatex -interaction=nonstopmode -halt-on-error "$report_name" >> "$report_name.build.log"
done
python3 ../src/check_report_layout.py
