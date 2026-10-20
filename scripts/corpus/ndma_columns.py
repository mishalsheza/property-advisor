"""Rebuild NDMA two-column reading order from pdftotext -bbox-layout output.
usage: python -I ndma_columns.py bbox.html first_pdf_page out.txt"""
import re, sys
import xml.etree.ElementTree as ET

src, first_page, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
xml = open(src, encoding="utf-8").read()
xml = re.sub(r"<!DOCTYPE[^>]*>", "", xml).replace('xmlns="http://www.w3.org/1999/xhtml"', "")
root = ET.fromstring(xml)
pages_out = []
for n, page in enumerate(root.iter("page")):
    width = float(page.get("width"))
    height = float(page.get("height"))
    blocks = []
    for block in page.iter("block"):
        x0, y0 = float(block.get("xMin")), float(block.get("yMin"))
        lines = [" ".join(w.text or "" for w in line.iter("word")) for line in block.iter("line")]
        blocks.append((x0, y0, float(block.get("xMax")), lines))
    # drop running header/footer bands (top/bottom 6% of the page)
    body = [b for b in blocks if height * 0.06 < b[1] < height * 0.94]
    left = sorted((b for b in body if b[0] < width * 0.45), key=lambda b: b[1])
    right = sorted((b for b in body if b[0] >= width * 0.45), key=lambda b: b[1])
    text = []
    for b in left + right:
        text.append("\n".join(b[3]))
    pages_out.append(f"=== PDF PAGE {first_page + n} ===\n" + "\n\n".join(text))
open(out, "w", encoding="utf-8").write("\n\n".join(pages_out))
