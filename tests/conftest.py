"""Shared pytest setup.

Forces DATABASE_URL to an isolated database before any test module imports
backend.api.main (and transitively backend.database.session, which reads
DATABASE_URL at import time). Without this, running the suite would
create/write to the real ./equitylens.db a developer might have from
running the app locally -- conftest.py is guaranteed by pytest to load
before any test module in this directory, so this is the one place that
import ordering is safe to rely on.

Deliberately a real (temp) file, not sqlite:///:memory:. FastAPI dispatches
each sync `def` route handler onto a worker thread, and SQLAlchemy's
default connection pool for an in-memory sqlite URL hands out one
connection per thread -- so a request handled on a worker thread would see
a *different*, empty in-memory database than the one this module's
init_db() populated from the main thread (confirmed: research_report
persistence silently no-opped under TestClient with :memory:, because
`no such table` was being swallowed by the "a DB hiccup must never break a
successful response" handling in backend/api/main.py). A temp file sidesteps
that entirely -- every thread's connection points at the same file on disk,
which is also what production's default DATABASE_URL uses (just a
permanent path instead of a temp one).
"""
import atexit
import os
import tempfile

_test_db_fd, _test_db_path = tempfile.mkstemp(suffix=".db", prefix="equitylens_test_")
os.close(_test_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_path}"


def _cleanup_test_db() -> None:
    try:
        os.remove(_test_db_path)
    except OSError:
        pass  # best-effort; a leftover temp file is harmless


atexit.register(_cleanup_test_db)
