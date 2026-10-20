# Data

## Synthetic demo data

`mock_properties.json` (35 properties, one per locality), `mock_market_trends.json`
(34 localities — Muzaffarpur is deliberately missing to exercise the retry path) and
`mock_risk_data.json` (34 localities) are **synthetic demo data**. Prices, rents,
appreciation rates and risk indicators were made up to cover the demo scenarios; they
are not sourced from any real listing or survey and must not be used for real
investment decisions.

## RAG corpus

`rag_corpus/` holds text converted from official and secondary source documents; see
`rag_corpus/sources.md` for provenance and what was trimmed. `rag_corpus_legacy/` keeps
the original AI-written notes for reference; they are no longer indexed.

## Price index

`rbi_hpi.csv` is parsed from the RBI House Price Index publication (city, quarter,
index_value, base_year, provisional). The market step uses the base 2022-23 series for
city-level appreciation rates, replacing the synthetic mock rate wherever a city has a series.
