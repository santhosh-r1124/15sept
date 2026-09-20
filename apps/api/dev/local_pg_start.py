"""Start (or reuse) an embedded PostgreSQL 16 + pgvector — no Docker needed.

Run with a Python that has ``pgserver`` wheels (cp39-cp312; NOT the project's 3.13 venv):

    uv run --no-project --python 3.12 --with pgserver python dev/local_pg_start.py

Prints the connection URI and records it in ``dev/.local-pg.json`` (gitignored) for
``local_pg_migrate.py``. The server keeps running after this script exits.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pgserver

HERE = pathlib.Path(__file__).resolve().parent
PGDATA = pathlib.Path.home() / ".legal_platform_pgdata"


def main() -> None:
    server = pgserver.get_server(PGDATA, cleanup_mode=None)
    uri = server.get_uri()
    server.psql("create extension if not exists vector;")
    (HERE / ".local-pg.json").write_text(json.dumps({"uri": uri}), encoding="utf-8")
    print(uri)
    print("Next: uv run python dev/local_pg_migrate.py", file=sys.stderr)


if __name__ == "__main__":
    main()
