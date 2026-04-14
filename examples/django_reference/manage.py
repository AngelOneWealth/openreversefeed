#!/usr/bin/env python
"""Django management entry point for the openreversefeed reference app."""
import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "reference_app.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django is not installed. Run `pip install 'django>=5,<6'` in the library venv."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
