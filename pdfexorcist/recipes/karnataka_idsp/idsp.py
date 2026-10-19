"""Karnataka IDSP weekly infectious disease report."""

import re
from collections.abc import Iterable, Iterator

from pdfexorcist.rows import Page

NUM = re.compile(r"^\d[\d,]*$")
MONTH = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$")
PERIODS = re.compile(r"^(Last Week|Last Month)\s+Current Year\b")
MEASURE = re.compile(r"Reported cases|Tested|Positives|Cases|Bites|Deaths")
WEEK = re.compile(r"Week No (\d+)")


def _title(words: list[str]) -> str:
    """What is left of a line once the trend charts' text is dropped: a disease name, or ''."""
    kept = []
    for w in words:
        w = w.split("(Source")[0]  # a section heading; COVID-19 has no box title under its own
        if w.startswith(("Trend of", "*")) or NUM.match(w) or MONTH.match(w):
            continue
        kept.extend(t for t in w.split() if not MONTH.match(t) and not NUM.match(t))
    # "s": a chart's stray letter; "division)": the end of a wrapped section heading
    title = " ".join(t for t in kept if len(t) > 1 or not t.islower())
    return "" if MEASURE.fullmatch(title) or (title.endswith(")") and "(" not in title) else title


def parse(pages: Iterable[Page]) -> Iterator[dict]:
    """Yield each disease's figures keyed by disease, period and measure."""
    week = None
    for page_no, lines in pages:
        disease = None
        periods: list[str] = []
        measures: list[str] = []
        for cells in lines:
            words = [s.strip() for _, s in cells if s.strip()]
            text = " ".join(words)
            if m := WEEK.search(text):
                week = m[1]
            if m := PERIODS.match(text):
                periods = [m[1].lower().replace(" ", "_"), "current_year"]
                measures = []
                continue
            if periods and not measures and len(found := MEASURE.findall(text)) % 2 == 0 and found:
                measures = [s.lower() for s in found]
                continue
            nums = [w for w in text.split() if NUM.match(w)]
            n = len(measures) or len(periods)
            if periods and disease and n and len(nums) >= n and text.split()[0] == nums[0]:
                names = measures or ["cases"] * n
                for i, v in enumerate(nums[:n]):
                    yield {
                        "disease": disease,
                        "period": periods[i * len(periods) // n],
                        "measure": names[i],
                        "value": v,
                        "page": page_no,
                        "week": week,
                    }
                periods = []
            elif t := _title(words):  # a new box, even if the last one gave no values
                disease = t.rstrip("*").strip()
                periods = []
