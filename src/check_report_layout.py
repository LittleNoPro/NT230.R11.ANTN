"""Check rendered PDF structure, not just LaTeX compilation success.

Requires Poppler's pdftotext. Figures/tables must precede references; appendix
tables are allowed after an explicit appendix heading. Visual inspection remains
necessary for typography, charts and other layout details.
"""
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCES = re.compile(r"\bR\s*E\s*F\s*E\s*R\s*E\s*N\s*C\s*E\s*S\b")
APPENDIX = re.compile(r"\bA\s*P\s*P\s*E\s*N\s*D\s*I\s*X\b")


def check_caption_order(text):
    heading = REFERENCES.search(text)
    if heading is None:
        raise ValueError("rendered PDF has no references heading")
    bibliography = APPENDIX.split(text[heading.end():], maxsplit=1)[0]
    if re.search(r"\bTABLE\s+[IVXLCDM]+\b|\bFig\.\s+\d+\.", bibliography):
        raise ValueError("a figure/table caption interrupts the bibliography")


def inspect_report(path):
    log = path.with_suffix(".log").read_text()
    if any(s in log for s in ("Overfull", "undefined", "LaTeX Warning", "Package balance Warning")):
        raise ValueError(f"unresolved typesetting warning: {path}")
    text = subprocess.check_output(["pdftotext", "-layout", str(path), "-"], text=True)
    check_caption_order(text)
    bbox = subprocess.check_output(["pdftotext", "-bbox-layout", str(path), "-"], text=True)
    pages = ET.fromstring(bbox).findall(".//{*}page")
    for number, page in enumerate(pages, 1):
        width, height = float(page.attrib["width"]), float(page.attrib["height"])
        words = page.findall(".//{*}word")
        if not words:
            raise ValueError(f"blank page: {path}, page {number}")
        for word in words:
            x0, y0, x1, y1 = (float(word.attrib[k]) for k in ("xMin", "yMin", "xMax", "yMax"))
            if min(x0, y0) < -0.5 or x1 > width + 0.5 or y1 > height + 0.5:
                raise ValueError(f"text outside page bounds: {path}, page {number}")
    result = dict(pages=len(pages), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  captions_before_references=True, text_within_page_bounds=True,
                  unresolved_typesetting_warnings=False)
    if path.stem == "main":
        page = pages[-1]
        midpoint = float(page.attrib["width"]) / 2
        words = page.findall(".//{*}word")
        bottoms = [max((float(w.attrib["yMax"]) for w in words if (
            float(w.attrib["xMax"]) <= midpoint if side == "left" else float(w.attrib["xMin"]) >= midpoint
        )), default=0) for side in ("left", "right")]
        if not all(bottoms) or abs(bottoms[0] - bottoms[1]) > 24:
            raise ValueError(f"unbalanced final columns: {path}: {bottoms}")
        result["final_column_bottom_difference_pt"] = round(abs(bottoms[0] - bottoms[1]), 2)
    return result


def main():
    reports = {f"report/{name}.pdf": inspect_report(ROOT / "report" / f"{name}.pdf")
               for name in ("main", "extended")}
    destination = ROOT / "results/report_layout.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(dict(status="passed", reports=reports,
        scope="rendered text structure and bounds; visual review is a separate step"), indent=2) + "\n")
    print("Rendered layout checks passed: captions, references, page bounds and final main-report columns")


if __name__ == "__main__":
    main()
