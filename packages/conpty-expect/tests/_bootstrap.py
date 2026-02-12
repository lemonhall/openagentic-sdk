from __future__ import annotations

import sys
from pathlib import Path


def ensure_src_on_syspath() -> None:
    # Allow running tests from the monorepo root without installing the package.
    # This keeps the subproject self-contained and avoids interfering with the main repo tooling.
    tests_dir = Path(__file__).resolve().parent
    src_dir = tests_dir.parent / "src"
    src = str(src_dir)
    if src not in sys.path:
        sys.path.insert(0, src)

