"""Parse the RBI House Price Index publication (pdftotext -bbox output) into CSV.

usage: python -I parse_hpi.py hpi_bbox.html out.csv

Layout (15 pages; 4, 5, 9, 10 blank):
  p1-3   base 2008-09 series (top, header y~162) and base 2010-11 series (bottom, header y~532)
  p6-8   base 2010-11 continued, no headers: column groups of p1, p2, p3 bottom headers
  p11-13 top: base 2010-11 continued (column groups of p1, p2, p3); below: base 2022-23 series
  p14-15 base 2022-23 only
Quarter labels appear only on the first page of each group (p1, p6, p11); rows on the
other pages are matched to them by y position.
"""

import csv
import re
import sys
import xml.etree.ElementTree as ET

src, out = sys.argv[1], sys.argv[2]
xml = re.sub(r"<!DOCTYPE[^>]*>", "", open(src, encoding="utf-8").read()).replace('xmlns="http://www.w3.org/1999/xhtml"', "")
PAGES = list(ET.fromstring(xml).iter("page"))
NUM = re.compile(r"^\d+\.\d+$")
QUARTER = re.compile(r"^Q[1-4]\.\d{4}-\d{2}")


def words(page_no):
    return [
        (float(w.get("xMin")), float(w.get("xMax")), float(w.get("yMin")), w.text)
        for w in PAGES[page_no - 1].iter("word")
    ]


def headers(page_no, y_lo, y_hi):
    """Cluster header words in a y band into [(x_center, name)]."""
    ws = sorted((w for w in words(page_no) if y_lo <= w[2] <= y_hi and not NUM.match(w[3])), key=lambda w: (w[0] + w[1]) / 2)
    clusters = []
    for w in ws:
        c = (w[0] + w[1]) / 2
        if clusters and c - clusters[-1]["c"][-1] < 40:
            clusters[-1]["w"].append(w)
            clusters[-1]["c"].append(c)
        else:
            clusters.append({"w": [w], "c": [c]})
    out_ = []
    for cl in clusters:
        name = " ".join(w[3] for w in sorted(cl["w"], key=lambda w: (round(w[2] / 5), w[0])))
        out_.append((sum(cl["c"]) / len(cl["c"]), name))
    return out_


def quarter_labels(page_no, y_lo, y_hi):
    return [(w[2], w[3]) for w in words(page_no) if QUARTER.match(w[3]) and y_lo <= w[2] <= y_hi]


def cells(page_no, y_lo, y_hi, cols, labels):
    rows = []
    for x0, x1, y, text in words(page_no):
        if not NUM.match(text) or not (y_lo <= y <= y_hi):
            continue
        center = (x0 + x1) / 2
        city = min(cols, key=lambda c: abs(c[0] - center))[1]
        label = min(labels, key=lambda l: abs(l[0] - y))
        assert abs(label[0] - y) < 4, (page_no, text, y)
        rows.append((city, label[1], float(text)))
    return rows


SERIES_A = ("2008-09", 150, 470)  # base, y range (p1-3 top)
SERIES_B_TOP = (520, 800)
records = []

labels_a = quarter_labels(1, *SERIES_A[1:])
labels_b1 = quarter_labels(1, 540, 800)
for p in (1, 2, 3):
    cols_a = headers(p, 150, 172)
    cols_b = headers(p, 520, 540)
    for city, q, v in cells(p, 175, 470, cols_a, labels_a):
        records.append(("2008-09", city, q, v))
    for city, q, v in cells(p, 545, 800, cols_b, labels_b1):
        records.append(("2010-11", city, q, v))

labels_b2 = quarter_labels(6, 0, 842)
for p, header_page in ((6, 1), (7, 2), (8, 3)):
    for city, q, v in cells(p, 0, 842, headers(header_page, 520, 540), labels_b2):
        records.append(("2010-11", city, q, v))

labels_b3 = quarter_labels(11, 0, 170)
labels_c = quarter_labels(11, 215, 520)
for p in (11, 12, 13, 14, 15):
    if p <= 13:
        for city, q, v in cells(p, 0, 170, headers(p - 10, 520, 540), labels_b3):
            records.append(("2010-11", city, q, v))
    for city, q, v in cells(p, 215, 520, headers(p, 195, 215), labels_c):
        records.append(("2022-23", city, q, v))

with open(out, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["city", "quarter", "index_value", "base_year", "provisional"])
    for base, city, q, v in records:
        provisional = "(P)" in q
        writer.writerow([city, re.sub(r"\(P\)\**$", "", q), f"{v:.2f}", base, str(provisional).lower()])

from collections import Counter
print(len(records), "rows")
for base in ("2008-09", "2010-11", "2022-23"):
    by_city = Counter(r[1] for r in records if r[0] == base)
    print(base, len(by_city), "cities:", dict(by_city))
