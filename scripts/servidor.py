"""Sobe o backend do Fabulim Studio (127.0.0.1). Usado por iniciar.bat / iniciar.sh."""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

from app.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
