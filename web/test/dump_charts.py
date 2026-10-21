import json
import sys
from pathlib import Path

from pdfexorcist.charts import read_charts


def main(root: Path) -> None:
    out = {}
    for pdf in sorted((root / "tests" / "fixtures").rglob("*.pdf")):
        df = read_charts(pdf)
        if len(df) or df.attrs["skipped"]:
            out[str(pdf.relative_to(root))] = [df.to_csv(index=False), df.attrs["skipped"]]
    json.dump(out, sys.stdout, sort_keys=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
