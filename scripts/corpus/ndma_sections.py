"""Split column-ordered NDMA text into numbered x.y sections.
usage: python -I ndma_sections.py ndma_cols.txt [sections.json]
  -> prints section number, first PDF page and word count; writes the split to sections.json"""
import re, sys, json
text = open(sys.argv[1], encoding="utf-8").read()
sections, cur, page = [], None, None
for line in text.split("\n"):
    m = re.match(r"=== PDF PAGE (\d+) ===", line)
    if m:
        page = int(m.group(1)); continue
    if re.match(r"^\d{1,2}\.\d{1,2}$", line.strip()):
        cur = {"num": line.strip(), "page": page, "lines": []}
        sections.append(cur); continue
    if cur is not None:
        cur["lines"].append(line)
for s in sections:
    title = " ".join(l for l in s["lines"][:4] if l.strip() and not re.match(r"^\d", l.strip()))[:50]
    print(s["num"], s["page"], len(" ".join(s["lines"]).split()), "|", title)
if len(sys.argv) > 2:
    json.dump(sections, open(sys.argv[2], "w"))
