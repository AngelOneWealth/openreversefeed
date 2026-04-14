"""File worker: polls source_files for status='pending' and processes them.

Run in a separate terminal alongside the Django server:

    export DJANGO_SETTINGS_MODULE=reference_app.settings
    python workers/file_worker.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import django

# Let this script run standalone from the examples/django_reference directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "reference_app.settings")
django.setup()

from sqlalchemy import select  # noqa: E402

from openreversefeed.db.models import SourceFile  # noqa: E402
from reference_app.ofr_bridge import get_session_factory, process_source_file  # noqa: E402


def main() -> None:
    print("file-worker starting, polling every 3s for pending files...")
    while True:
        Session = get_session_factory()
        with Session() as session:
            pending = (
                session.execute(select(SourceFile).where(SourceFile.status == "pending"))
                .scalars()
                .all()
            )
            if pending:
                print(f"  {len(pending)} pending file(s)")
                for sf in pending:
                    print(f"    processing id={sf.id} ({sf.filename})")
                    result = process_source_file(sf.id)
                    print(f"    result: {result}")
        time.sleep(3)


if __name__ == "__main__":
    main()
