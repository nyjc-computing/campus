"""campus-client.py

This python script is a convenience wrapper for the Campus API client.

It is meant to be run in python interactive mode, i.e.

$ python -i scripts/campus-client.py

Note that for it to be able to import the `campus` package, it must be run from the project root directory.
"""

import os

# Make a best-guess effort to check that current directory is project root.
if not os.path.exists("scripts/campus-client.py"):
    raise RuntimeError("campus-client must be run from project root")

from campus.client import Campus

campus = Campus()
campus.circles.list()
