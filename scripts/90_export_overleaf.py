"""Export outputs/ to outputs/overleaf/ (booktabs tables, figures, numbers.tex). Policy §13: numbers never typed by hand.

Usage:  uv run python scripts/90_export_overleaf.py
Reads outputs/tables/*.csv, outputs/figures/*.{pdf,png}, outputs/numbers.json; never fabricates a value.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from alj.export_overleaf import export_all  # noqa: E402

if __name__ == "__main__":
    print(json.dumps(export_all(), indent=2, ensure_ascii=False))
