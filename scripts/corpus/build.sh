#!/usr/bin/env bash
# Rebuild the RAG corpus and rbi_hpi.csv from the source PDFs in raw_docs/.
# usage: scripts/corpus/build.sh [OUT_DATA_DIR]   (default: src/property_advisor/data)
# Requires poppler (pdftotext) and python3. sources.md is hand-written and not touched.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
RAW_DOCS="${RAW_DOCS:-$ROOT/raw_docs}"
OUT="${1:-$ROOT/src/property_advisor/data}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$WORK/raw" "$OUT/rag_corpus"

# 1. Plain layout text for every PDF (input to build_corpus.py, named after the PDF)
for pdf in "$RAW_DOCS"/*.pdf; do
  name="$(basename "$pdf" .pdf)"
  pdftotext -layout "$pdf" "$WORK/raw/$name.txt" 2>/dev/null
done

# 2. NDMA guideline is two-column: rebuild reading order from word boxes (PDF pages 29-113
#    = printed pages 1-85, chapters 1-6), then split into numbered sections
pdftotext -bbox-layout -f 29 -l 113 "$RAW_DOCS/management_urban_flooding.pdf" "$WORK/ndma.html"
python3 -I "$HERE/ndma_columns.py" "$WORK/ndma.html" 29 "$WORK/ndma_cols.txt"
python3 -I "$HERE/ndma_sections.py" "$WORK/ndma_cols.txt" "$WORK/sections.json" > /dev/null

# 3. Clean everything into corpus files
python3 -I "$HERE/build_corpus.py" "$WORK/raw" "$WORK/sections.json" "$OUT/rag_corpus"

# 4. House Price Index table -> CSV (not part of the corpus)
pdftotext -bbox "$RAW_DOCS/House Price Index Publication.pdf" "$WORK/hpi.html"
python3 -I "$HERE/parse_hpi.py" "$WORK/hpi.html" "$OUT/rbi_hpi.csv"

echo "Done. Delete chroma_db/ so the index is rebuilt from the new corpus."
