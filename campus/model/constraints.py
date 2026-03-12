"""campus.model.constraints

Defines constraints used in Campus models.
"""

UNIQUE = "unique"


class Constraint:
    """Base class for all constraints."""


class Unique(Constraint):
    """Constraint that ensures a set of fields are unique across all
    records.
    """
    fields: tuple[str, ...]

    def __init__(self, *fields: str):
        self.fields = fields
