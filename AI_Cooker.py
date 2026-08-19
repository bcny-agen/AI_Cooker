"""Backward-compatible command-line entry point for AI_Cooker.

The reusable implementation lives in the ``app`` package. Importing this file is
safe: the demo runs only when the file is executed directly.
"""

from app.demo import main


if __name__ == "__main__":
    raise SystemExit(main())
