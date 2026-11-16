"""Unit tests for campus.auth.

Storage mode must be set BEFORE any campus.auth resource module is
imported: the resource modules call get_table/get_collection at import
time, binding the backend for the process (unittest has no conftest).
SQLite/memory test backends; no real Postgres/Mongo is touched.
"""
import os

os.environ.setdefault("STORAGE_MODE", "1")
