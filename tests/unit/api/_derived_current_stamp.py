"""Process-global monotonic created_at stamps for derived-current tests.

Windows's ~15.6 ms system-clock tick makes back-to-back utc_time.now()
calls return the identical value, so timetable versions created by fast
tests can share an identical clock-stamped created_at — and the
derived-current ordering (#1222: latest start_date, created_at breaking
exact ties, compared at SGT-date granularity) degenerates to storage row
order. Tests that need a deterministic derived-current pick stamp their
versions with stamp(): one shared counter orders every create in the
process, and the anchor sits 60 s ahead of the import instant so the
stamps also beat anything an earlier test stored from the real clock.
"""

import datetime
import itertools

from campus.common.utils import utc_time

_ANCHOR = utc_time.now()
_SEQ = itertools.count()


def stamp() -> datetime.datetime:
    """A strictly increasing timestamp, unique per call in the process."""
    return _ANCHOR + datetime.timedelta(seconds=60 + next(_SEQ))
