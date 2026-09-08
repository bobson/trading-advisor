#!/usr/bin/env python3
"""Phase 24 — run the API server.

Binds 127.0.0.1:8000 by default (localhost only — put nginx in front on the droplet). Override
with env vars so it never collides with the other server on your droplet:

    API_HOST=127.0.0.1 API_PORT=8010 python scripts/serve.py

or directly:  uvicorn src.api.app:app --host 127.0.0.1 --port 8010
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402


def main() -> None:
    uvicorn.run(
        "src.api.app:app",
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=bool(os.getenv("API_RELOAD")),
    )


if __name__ == "__main__":
    main()
