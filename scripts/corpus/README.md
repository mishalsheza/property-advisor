# Corpus build scripts

Rebuild `src/property_advisor/data/rag_corpus/*.txt` and `src/property_advisor/data/rbi_hpi.csv`
from the source PDFs in `raw_docs/` (not committed — see `rag_corpus/sources.md` for where each
PDF came from).

```bash
scripts/corpus/build.sh            # writes into src/property_advisor/data/
scripts/corpus/build.sh /tmp/out   # or into another directory, e.g. to diff first
rm -rf chroma_db                   # then let the app re-index the new corpus
```

Requires `pdftotext` (poppler) and `python3` (standard library only). The output is
deterministic: rerunning on the same PDFs reproduces the committed files exactly.
`sources.md` is hand-written and never overwritten. "no word list" messages come from blank
pages in the HPI PDF and are harmless.

| Script | Does |
|---|---|
| `build.sh` | Runs everything below in a temp dir |
| `ndma_columns.py` | Rebuilds two-column reading order for the NDMA guideline from `pdftotext -bbox-layout` word boxes (`-layout` interleaves the columns) |
| `ndma_sections.py` | Splits the NDMA text into numbered `x.y` sections and prints word counts (useful when choosing sections) |
| `build_corpus.py` | Per-document cleaning of `pdftotext -layout` output: letterheads, watermark fragments, page numbers, running headers, site navigation; merges the House Property pages; selects NDMA sections (`NDMA_KEEP`); adds provenance / WITHDRAWN header lines |
| `parse_hpi.py` | Parses the RBI House Price Index tables (`pdftotext -bbox`) into `city, quarter, index_value, base_year, provisional` |

The cleaning rules are tied to these specific PDFs (filenames, page ranges, column offsets, a
few hand-restored lines listed in `sources.md`). A new or updated PDF needs its own function in
`build_corpus.py`; check the output by eye and update `sources.md`.
