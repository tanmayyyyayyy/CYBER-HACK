"""Run the app with disposable storage for a manual browser check."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main() -> int:
    with tempfile.TemporaryDirectory(prefix="drishti-ui-check-") as data_dir:
        os.environ["DRISHTI_DATA_DIR"] = str(Path(data_dir) / "data")
        from scripts.run_local import main as run_local

        return run_local()


if __name__ == "__main__":
    raise SystemExit(main())
