"""Enable ``python -m tallyimporter``."""

from __future__ import annotations

from tallyimporter.cli import main

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
