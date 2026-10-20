"""Clean pdftotext output into RAG corpus files.

usage: python -I build_corpus.py RAW_DIR SECTIONS_JSON OUT_DIR
RAW_DIR holds `pdftotext -layout` output named after each PDF;
SECTIONS_JSON is the NDMA section split from ndma_sections.py.
"""

import json
import re
import sys
from pathlib import Path

RAW, SECTIONS, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
OUT.mkdir(parents=True, exist_ok=True)

WITHDRAWN = "WITHDRAWN / SUPERSEDED — historical reference only; not the current RBI limit."
WATERMARK_FRAGMENTS = {"W", "Wi", "ith", "ithdr", "dr", "aw", "awn", "n", "Withdrawn"}
# Hindi letterhead text, either real Devanagari or the legacy-font mojibake RBI PDFs produce
HINDI = re.compile(r"[ऀ-ॿ]|[ž¸£·ú¡¹¨Ä¤ÿˆÅ½¥ûø›¾Æ¬]")
PAGE_NUMBER = re.compile(r"^\s*-?\s*([0-9]{1,3}|[ivxlc]{1,6})\s*-?\s*$")


def read(name: str) -> str:
    return (RAW / name).read_text(encoding="utf-8")


def strip_watermark(line: str) -> str:
    segments = re.split(r"(\s{2,})", line)
    kept = "".join(s for s in segments if s.strip() not in WATERMARK_FRAGMENTS)
    # one fragment is glued to a sentence by a single space: "enclosed. n"
    return re.sub(r"(?<=[.;:)])\s(n|aw|W|ithdr)\s*$", "", kept)


def collapse(line: str) -> str:
    """Wide gaps (table columns) become ' | ', other runs of spaces one space."""
    line = re.sub(r"(?<=\S)\s{8,}(?=\S)", " | ", line.strip())
    # a paragraph number followed by its (indented) text is not a table cell
    line = re.sub(r"^(\(?[0-9ivx.]+\)?) \| ", r"\1 ", line)
    return re.sub(r"\s{2,}", " ", line)


def finish(lines: list[str]) -> str:
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # a blank line left where a page header/number was removed, mid-sentence
    text = re.sub(r"\n\n(?=[a-z])", "\n", text)
    return text.strip() + "\n"


def write(name: str, header: list[str], body: str) -> None:
    (OUT / name).write_text("\n".join(header) + "\n\n" + body, encoding="utf-8")


# ---------------------------------------------------------------- RBI circulars


def rbi_circular(raw: str, drop_extra: list[re.Pattern]) -> str:
    out = []
    for line in raw.replace("\f", "\n").split("\n"):
        if HINDI.search(line) or PAGE_NUMBER.match(line):
            continue
        if re.match(r"^\s*_{5,}", line) or "RESERVE BANK OF INDIA" in line or line.strip() == "www.rbi.org.in":
            continue
        if re.search(r"Department of Banking (Operations|Regulation)|Shahid Bhagat Singh Marg|Tel No", line):
            continue
        if any(p.search(line) for p in drop_extra):
            continue
        unmarked = strip_watermark(line)
        if line.strip() and not unmarked.strip():
            continue  # the whole line was watermark debris; don't leave a blank line mid-sentence
        out.append(collapse(unmarked).replace("` ", "₹").replace("`", "₹"))
    return finish(out)


def master_circular_2014() -> None:
    raw = read("68MH01072014F.txt")
    # drop the CONTENTS page (a page-number index of the sections listed again under "Structure")
    start = raw.index("CONTENTS")
    end = raw.index("A. Purpose")
    raw = raw[:start] + raw[end:]
    # drop the Annex (blank statistical reporting form) and Appendix (table of old circular numbers):
    # their multi-column tables convert to unreadable fragments
    raw = raw[: re.search(r"\n\s*Annex\s*\n", raw).start()]
    body = rbi_circular(raw, [re.compile(r"DBOD-MC-Housing Finance - 2014"), re.compile(r"^\s*Master Circular – Housing Finance\s*$")])
    # LTV table row wrapped by the layout ("Above ₹20 lakh & upto ₹75 80" / "lakh"), restored from the PDF
    body = body.replace("Above ₹20 lakh & upto ₹75 80\nlakh", "Above ₹20 lakh & upto ₹75 lakh | 80")
    write(
        "rbi_housing_finance_master_circular_2014.txt",
        [WITHDRAWN, "Master Circular – Housing Finance (RBI/2014-15/68, DBOD.No.DIR.BC.18/08.12.001/2014-15), Reserve Bank of India, July 1, 2014."],
        body,
    )


def ltv_2012() -> None:
    write(
        "rbi_ltv_circular_2012.txt",
        [WITHDRAWN, "Housing Loans by Commercial Banks – Loan to Value (LTV) Ratio (RBI/2011-12/383), Reserve Bank of India, February 3, 2012."],
        rbi_circular(read("HLB03022012.txt"), []),
    )


def ltv_2015() -> None:
    write(
        "rbi_ltv_riskweights_circular_2015.txt",
        [WITHDRAWN, "Individual Housing Loans: Rationalisation of Risk-Weights and LTV Ratios (RBI/2015-16/200), Reserve Bank of India, October 8, 2015."],
        rbi_circular(read("NT200993E78621BA84ED5BD93E6E70B7C4F33.txt"), []),
    )


def press_release(src: str, out: str, title: str) -> None:
    raw = read(src)
    # drop Chart 1 (axis labels and data points have no reading order)
    raw = re.sub(r"\n[^\n]*Chart 1: All-India House Price Index.*?P - Provisional[^\n]*", "\n", raw, flags=re.S)
    lines = []
    for line in raw.split("\n"):
        if HINDI.search(line) or "PRESS RELEASE" in line or "RESERVE BANK OF INDIA" in line:
            continue
        if re.search(r"Website :|email :|Mumbai - 400 001|Department of Communication", line):
            continue
        lines.append(collapse(re.sub(r"^\s*•\s*", "- ", line)))
    write(out, [title], finish(lines))


# ---------------------------------------------------------------- Income tax pages


def house_property() -> None:
    seen, paragraphs = set(), []
    # "Computation" page first, then "Interest on Housing Loan"
    for src in ("House Property2.txt", "House Property.txt"):
        raw = read(src)
        lines = raw.split("\n")
        start = next(i for i, l in enumerate(lines) if "Last Updated" in l) + 1
        end = next(i for i, l in enumerate(lines) if "Public Awareness" in l)
        current: list[str] = []
        for line in lines[start:end]:
            content = line[46:].strip()  # left 46 columns are the site's navigation sidebar
            if not line.strip():
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
                continue
            if content:
                current.append(re.sub(r"\s{2,}", " ", content))
        if current:
            paragraphs.append(" ".join(current))
    out = []
    for p in paragraphs:
        key = re.sub(r"\W+", " ", p).lower().strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    write(
        "income_tax_house_property.txt",
        ["Income from House Property — Income Tax Department, Government of India (incometaxindia.gov.in tax reckoner pages), last updated May 27, 2026."],
        "\n\n".join(out) + "\n",
    )


# ---------------------------------------------------------------- PRS brief


def model_tenancy() -> None:
    pages = read("Legislative Brief - Model Tenancy Act 2021.txt").split("\f")
    sidebar, out, in_sidebar = [], [], True
    for line in pages[0].split("\n")[2:]:
        # page footer (indented); author e-mails in the sidebar share lines with body text, so only
        # indented lines are footer
        if line.startswith(" ") and re.search(r"PRS Legislative Research|Gandharva Mahavidyalaya|prsindia\.org", line):
            continue
        m = re.match(r"^(\S.*?)(\s{3,})(\S.*)?$", line)
        if m and not line.startswith(" "):
            left, right = m.group(1), m.group(3) or ""
        elif not line.startswith(" "):
            left, right = line.strip(), ""
        else:
            left, right = "", line.strip()
        if left.startswith("Recent Briefs"):
            in_sidebar = False  # rest of the sidebar: other briefs, authors, emails, date
        if left and in_sidebar:
            sidebar.append(left)
        if right:
            out.append(collapse(right))
    body = [" ".join(sidebar), ""] + out
    for page in pages[1:]:
        for line in page.split("\n"):
            if re.search(r"The Model Tenancy Act, 2021\s+PRS Legislative Research|June 8, 2021\s+-\d+-", line):
                continue
            if PAGE_NUMBER.match(line):
                continue
            body.append(collapse(line))
    # PRS bullets are private-use-area glyphs (U+F0A7, U+F0AE, U+F06E)
    text = re.sub("[\ue000-\uf8ff]", "-", "\n".join(body))
    # endnotes (numbered source URLs) and the PRS disclaimer
    text = text[: text.index("1. The Constitution of India")]
    write(
        "model_tenancy_act_2021_prs.txt",
        ["The Model Tenancy Act, 2021 — Legislative Brief, PRS Legislative Research, June 8, 2021."],
        finish(text.split("\n")),
    )


# ---------------------------------------------------------------- iPleaders RERA explainer


def rera_explainer() -> None:
    raw = read("rera.txt").replace("\f", "\n")
    lines = raw.split("\n")
    start = next(i for i, l in enumerate(lines) if l.strip() == "Introduction" and i > 80)
    end = max(i for i, l in enumerate(lines) if l.strip() == "References")
    body = [collapse(l) for l in lines[start:end]]
    write(
        "rera_act_2016_explainer.txt",
        [
            "Real Estate (Regulation and Development) Act, 2016 — explainer article, iPleaders blog, May 21, 2022.",
            "SECONDARY SOURCE: a law-student blog summary, not the text of the Act.",
        ],
        finish(body),
    )


# ---------------------------------------------------------------- NDMA excerpt

NDMA_KEEP = ["1.2", "1.3", "1.6", "4.18", "4.23", "5.4", "5.5", "5.8", "6.1", "6.3", "6.4", "6.5", "6.6", "6.7"]
# justified lines that pdftotext split into single letters, restored by hand from the PDF
NDMA_LETTER_FIXES = {
    "b a n k f l o w, c h a n n e l": "bank flow, channel",
    "Pr o v i s i o n s f o r p r e p a r a t i o n o f": "Provisions for preparation of",
    "D e v e l o p m e n t P l a n s Fo r m u l a t i o n a n d": "Development Plans Formulation and",
    "c h a n n el i z a t i o n o f nallahs/": "channelization of nallahs/",
    "o f a l a ke , a r i n g r o a d o r": "of a lake, a ring road or",
}
# running page headers (printed in small caps, which pdftotext splits as "N ational D isaster ...")
NDMA_RUNNING_HEADERS = {
    "national disaster management guidelines: management of urban flooding",
    "introduction",
    "design and management of urban drainage system",
    "urban flood disaster risk management",
    "techno-legal regime",
}


def _is_running_header(line: str) -> bool:
    # small caps also put stray spaces around ":" and "-", so compare with all spaces removed
    return re.sub(r"\s+", "", line).lower() in {re.sub(r"\s+", "", h) for h in NDMA_RUNNING_HEADERS}


def ndma_excerpt() -> list[str]:
    sections = {s["num"]: s for s in json.loads(SECTIONS.read_text())}
    parts = []
    for num in NDMA_KEEP:
        paragraphs, current = [], []
        lines = sections[num]["lines"]
        if num == "1.3":
            # Table 1.1 is a two-column grid of bullet lists whose cells interleave; keep caption and source
            start = next(i for i, l in enumerate(lines) if l.startswith("Table 1.1"))
            end = next(i for i, l in enumerate(lines) if l.startswith("Source: Adapted"))
            lines = lines[: start + 1] + ["", "[Table body omitted: two-column list of meteorological, hydrological and human factors.]", ""] + lines[end:]
        for line in lines + [""]:
            line = NDMA_LETTER_FIXES.get(line.strip(), line.strip())
            if line and (_is_running_header(line) or PAGE_NUMBER.match(line)):
                continue
            if not line:
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
                continue
            current.append(line)
        # a bare paragraph number ("1.6.1") belongs to the paragraph after it
        merged: list[str] = []
        for p in paragraphs:
            marker = merged and re.fullmatch(r"[\d.]+|•|\(?[a-z0-9]{1,4}\)", merged[-1])
            if marker or (merged and p[0].islower()):
                # also rejoin a sentence that a removed page header split in two
                merged[-1] = f"{merged[-1]} {p}"
            else:
                merged.append(p)
        title, rest = merged[0], merged[1:]
        parts.append(f"{num} {title}\n\n" + "\n\n".join(rest))
    write(
        "ndma_urban_flooding_excerpt.txt",
        [
            "National Disaster Management Guidelines: Management of Urban Flooding — National Disaster Management Authority (NDMA), Government of India, September 2010.",
            "EXCERPT: sections " + ", ".join(NDMA_KEEP) + " only (buyer-relevant: land use, encroachment, flood-prone zoning, building regulations, urban sprawl).",
        ],
        "\n\n".join(parts) + "\n",
    )
    return NDMA_KEEP


master_circular_2014()
ltv_2012()
ltv_2015()
press_release("PR2167E2AC62A4A8794DCFB241D037047AC6B8.txt", "rbi_hpi_press_release_q3_2025_26.txt",
              "All-India House Price Index for Q3:2025-26 — RBI press release 2025-2026/2167, February 25, 2026.")
press_release("PR355BA75B6F6F6514EF69A5D859B97C10F89.txt", "rbi_hpi_press_release_q4_2025_26.txt",
              "All-India House Price Index for Q4:2025-26 — RBI press release 2026-2027/355, May 29, 2026.")
press_release("PR9588D145628AA3348AC8BD8DB564DF6DD75.txt", "rbi_hpi_press_release_q1_2026_27.txt",
              "All-India House Price Index for Q1:2026-27 — RBI press release 2026-2027/958, August 24, 2026.")
house_property()
model_tenancy()
rera_explainer()
ndma_excerpt()
for f in sorted(OUT.glob("*.txt")):
    print(f"{len(f.read_text(encoding='utf-8').split()):6d}  {f.name}")
