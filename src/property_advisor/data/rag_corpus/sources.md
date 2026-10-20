# RAG corpus sources

Every `.txt` file in this folder was converted from a PDF in `raw_docs/` (not committed) with
`pdftotext -layout`, then cleaned. Each file starts with a one-line provenance header (title,
issuer, date) added during conversion; RBI LTV circulars also start with a WITHDRAWN line.

URL status: **verified** = fetched or confirmed during the rebuild (2026-10-20);
**inferred** = built from the document ID in the original filename, not reachable from the build
machine — check before citing.

## Documents

### rbi_housing_finance_master_circular_2014.txt
- **Title:** Master Circular – Housing Finance (RBI/2014-15/68, DBOD.No.DIR.BC.18/08.12.001/2014-15)
- **Issuer:** Reserve Bank of India, Department of Banking Operations and Development
- **Date:** July 1, 2014
- **URL (inferred):** https://rbidocs.rbi.org.in/rdocs/notification/PDFs/68MH01072014F.pdf
- **Type:** Primary
- **Status:** WITHDRAWN / SUPERSEDED. The PDF carries RBI's "Withdrawn" watermark; later master
  circulars replaced it. Not the current LTV limit.
- **Trimmed:** Hindi/English letterhead and footer, "Withdrawn" watermark fragments, page numbers,
  running header ("DBOD-MC-Housing Finance - 2014"), the CONTENTS page (page-number index), the
  Annex (blank statistical reporting form) and the Appendix (table of earlier circular numbers);
  both tables convert to unreadable fragments. Rupee glyph (rendered as a backtick) mapped to ₹.
  One LTV table row wrapped by the layout was restored by hand: "Above ₹20 lakh & upto ₹75 lakh | 80".

### rbi_ltv_circular_2012.txt
- **Title:** Housing Loans by Commercial Banks – Loan to Value (LTV) Ratio (RBI/2011-12/383, DBOD.No.BP.BC.78/08.12.001/2011-12)
- **Issuer:** Reserve Bank of India
- **Date:** February 3, 2012
- **URL (inferred):** https://rbidocs.rbi.org.in/rdocs/notification/PDFs/HLB03022012.pdf
- **Type:** Primary
- **Status:** WITHDRAWN / SUPERSEDED ("Withdrawn" watermark). Historical reference only.
- **Trimmed:** footer letterhead, watermark fragments ("W", "ithdr", "aw", "n").

### rbi_ltv_riskweights_circular_2015.txt
- **Title:** Individual Housing Loans: Rationalisation of Risk-Weights and LTV Ratios (RBI/2015-16/200, DBR.BP.BC.No.44/08.12.015/2015-16)
- **Issuer:** Reserve Bank of India, Department of Banking Regulation
- **Date:** October 8, 2015
- **URL (inferred):** https://rbidocs.rbi.org.in/rdocs/notification/PDFs/NT200993E78621BA84ED5BD93E6E70B7C4F33.PDF
- **Type:** Primary
- **Status:** WITHDRAWN / SUPERSEDED ("Withdrawn" watermark). Historical reference only.
- **Trimmed:** Hindi/English footer letterhead, watermark fragments (including a stray "W" in the
  table header). Table columns are separated with " | ".

### rbi_hpi_press_release_q3_2025_26.txt / _q4_2025_26.txt / _q1_2026_27.txt
- **Title:** All-India House Price Index for Q3:2025-26 / Q4:2025-26 / Q1:2026-27
- **Issuer:** Reserve Bank of India, Department of Communication (press releases 2025-2026/2167, 2026-2027/355, 2026-2027/958)
- **Date:** February 25, 2026 / May 29, 2026 / August 24, 2026
- **URL (inferred):**
  - https://rbidocs.rbi.org.in/rdocs/PressRelease/PDFs/PR2167E2AC62A4A8794DCFB241D037047AC6B8.PDF
  - https://rbidocs.rbi.org.in/rdocs/PressRelease/PDFs/PR355BA75B6F6F6514EF69A5D859B97C10F89.PDF
  - https://rbidocs.rbi.org.in/rdocs/PressRelease/PDFs/PR9588D145628AA3348AC8BD8DB564DF6DD75.PDF
- **Type:** Primary
- **Trimmed:** Hindi/English letterhead; Chart 1 in the Q1:2026-27 release (axis labels and data
  points with no reading order). Note: Q4:2025-26 was provisional (115.9) in the May release and is
  116.2 in later data.

### income_tax_house_property.txt
- **Title:** Income from House Property (tax reckoner pages: "Computation of Income from House Property" and "Interest on Housing Loan")
- **Issuer:** Income Tax Department, Ministry of Finance, Government of India
- **Date:** pages "Last Updated: May 27th, 2026" (printed October 2026)
- **URL (inferred):** https://incometaxindia.gov.in — tax information & services › reckoner › house property (exact page URL not recorded in the PDFs; the site returned 403 to automated checks)
- **Type:** Primary
- **Trimmed:** merged from two PDFs (`House Property.pdf`, `House Property2.pdf`). The left
  navigation sidebar, top menu ("Home", "Tax Information & Services", "Reckoner"), footer
  ("Tutorials", "Tax Tools", "Sitemap", "Report Phishing", "RTI", "Contact Us", policies,
  copyright) were removed. The two pages shared only navigation/header/footer; no body paragraph
  appeared on both, so de-duplication removed no content.
- **Caveat:** cites section numbers of the Income-tax Act, 1961 (e.g. 24(b), 115BAC). Check
  against the Income-tax Act, 2025 for tax years from 2026-27 before relying on section numbers.

### model_tenancy_act_2021_prs.txt
- **Title:** Legislative Brief — The Model Tenancy Act, 2021
- **Issuer:** PRS Legislative Research
- **Date:** June 8, 2021
- **URL (verified):** https://prsindia.org/files/bills_acts/bills_parliament/2021/Legislative%20Brief%20-%20Model%20Tenancy%20Act%202021.pdf
- **Type:** Secondary (independent analysis of a model Act; the Act itself only applies where a state adopts it)
- **Trimmed:** page-1 sidebar "Recent Briefs" list and author names/e-mails (the sidebar summary
  sentence is kept), PRS address footer, running headers, page footers, endnotes (numbered source
  URLs), disclaimer. Bullet glyphs mapped to "-". Tables 1–2 keep their text but multi-line
  cells interleave.

### rera_act_2016_explainer.txt
- **Title:** Real Estate (Regulation and Development) Act, 2016 (blog explainer)
- **Issuer:** iPleaders blog; written by Akshaya V (LLB student, CMR University), published by Rachit Garg
- **Date:** May 21, 2022
- **URL (matched by title search):** https://blog.ipleaders.in/real-estate-regulation-and-development-act-2016-2/
- **Type:** Secondary — a law-student summary, **not the text of the Act**. Penalty and
  procedure descriptions are paraphrased and may be imprecise.
- **Trimmed:** site navigation, breadcrumbs, author/publisher byline, date/view-count/comment-count
  line, table of contents, References list, LawSikho promotion, tags, previous/next article
  links, "More from author", comment form, copyright footer.

### ndma_urban_flooding_excerpt.txt
- **Title:** National Disaster Management Guidelines: Management of Urban Flooding
- **Issuer:** National Disaster Management Authority (NDMA), Government of India
- **Date:** September 2010
- **URL (verified):** https://ndma.gov.in/sites/default/files/PDF/Guidelines/management_urban_flooding.pdf
- **Type:** Primary
- **Trimmed:** the full guideline is ~69,000 words. Kept only these sections (6,825 words):
  - 1.2 Urban Flooding is Different
  - 1.3 Contributory Factors (Table 1.1 body omitted — interleaved two-column grid)
  - 1.6 Urbanisation and Pressure on Land
  - 4.18 Water Bodies
  - 4.23 Encroachments
  - 5.4 Vulnerability Analysis and Risk Assessment
  - 5.5 Estimation of Possible Inundation Levels
  - 5.8 Reducing Vulnerability (incl. 5.8.4 Insurance and Risk Transfer)
  - 6.1 Overview (Techno-Legal Regime)
  - 6.3 Legal Support for Planned Development of Urban Areas
  - 6.4 Central Legislations/Guidelines (Model Town & Country Planning Act, NBC, building byelaws)
  - 6.5 Study by Experts Committee (2004)
  - 6.6 Subsequent Amendments (layout approvals and building permissions)
  - 6.7 Urban Sprawl

  Everything else (foreword, early warning systems, drainage design, response, capacity
  building, implementation, action-point summary, contributors) was dropped.
- **Conversion note:** the guideline is two-column. `pdftotext -layout` keeps the columns side by
  side, interleaving their lines, so this file was built from `pdftotext -bbox-layout` with
  blocks re-ordered left column then right column. Running headers (small caps) and page numbers
  removed; five justified lines that pdftotext split into single letters were restored by hand
  (e.g. "Pr o v i s i o n s f o r" → "Provisions for").

## Excluded

- **`the-real-estate-regulation-and-development-act-2016-…-bare-act-….pdf`** (ibclaw.in): lists only
  chapter and section titles, not the text of the Act. Excluded.
- **`House Price Index Publication.pdf`** (RBI): a city × quarter table, not prose. Parsed into
  `../rbi_hpi.csv` instead of being indexed.

## Known gaps

- **Official RERA Act text.** The corpus has only a secondary blog explainer. The Real Estate
  (Regulation and Development) Act, 2016 as published in the Gazette / India Code should be added.
- **Current RBI housing-finance rules.** The latest (2024) RBI Master Circular on Housing Finance
  is not in the corpus. All three RBI LTV/housing-finance documents here are withdrawn/superseded
  and must not be quoted as current limits.
- **Karnataka RERA Rules, 2017.** `06_-_RERA_Karnataka_Act_2017.pdf` was not in `raw_docs/`, so no
  state RERA rules are included.
- **Income-tax Act, 2025.** The house-property pages cite 1961 Act section numbers.
