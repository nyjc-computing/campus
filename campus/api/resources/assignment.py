"""campus.api.resources.assignment

Assignment resource for Campus API.
"""

import typing
from dataclasses import asdict

from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import uid
import campus.model
import campus.storage

assignment_storage = campus.storage.get_collection("assignments")


def _from_record(record: dict) -> campus.model.Assignment:
    """Convert a storage record to an Assignment model instance."""
    questions = [
        campus.model.Question(
            id=q["id"],
            prompt=q["prompt"],
            question=q["question"]
        )
        for q in record.get("questions", [])
    ]

    classroom_links = [
        campus.model.ClassroomLink(
            course_id=l["course_id"],
            coursework_id=l["coursework_id"],
            attachment_id=l.get("attachment_id"),
            linked_at=schema.DateTime(l["linked_at"])
        )
        for l in record.get("classroom_links", [])
    ]

    return campus.model.Assignment(
        id=schema.CampusID(record['id']),
        created_at=schema.DateTime(record['created_at']),
        title=record['title'],
        description=record.get('description', ''),
        questions=questions,
        created_by=schema.UserID(record['created_by']),
        updated_at=schema.DateTime(record['updated_at']),
        classroom_links=classroom_links
    )


class AssignmentsResource:
    """Represents the assignments resource in Campus API Schema."""

    @staticmethod
    def init_storage() -> None:
        """Initialize storage for assignments."""
        assignment_storage.init_collection()

    def __getitem__(self, assignment_id: schema.CampusID) -> "AssignmentResource":
        return AssignmentResource(assignment_id)

    def list(self, **filters: typing.Any) -> list[campus.model.Assignment]:
        """List all assignments matching filters."""
        try:
            records = assignment_storage.get_matching(filters)
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        return [_from_record(record) for record in records]

    def new(self, **fields: typing.Any) -> campus.model.Assignment:
        """Create a new assignment."""
        assignment = campus.model.Assignment(
            id=schema.CampusID(
                uid.generate_category_uid("assignment", length=8)
            ),
            created_at=schema.DateTime.utcnow(),
            title=fields["title"],
            description=fields.get("description", ""),
            questions=[
                campus.model.Question(**q)
                for q in fields.get("questions", [])
            ],
            created_by=schema.UserID(fields["created_by"]),
            updated_at=schema.DateTime.utcnow(),
            classroom_links=[
                campus.model.ClassroomLink(**l)
                for l in fields.get("classroom_links", [])
            ]
        )

        try:
            assignment_storage.insert_one(assignment.to_storage())
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

        return assignment


class AssignmentResource:
    """Represents a single assignment in Campus API Schema."""

    def __init__(self, assignment_id: schema.CampusID):
        self.assignment_id = assignment_id

    def get(self) -> campus.model.Assignment:
        """Get the assignment record."""
        try:
            record = assignment_storage.get_by_id(self.assignment_id)
            if record is None:
                raise api_errors.ConflictError(
                    "Assignment not found",
                    id=self.assignment_id
                )
            return _from_record(record)
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Assignment not found",
                id=self.assignment_id
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    def update(self, **updates: typing.Any) -> None:
        """Update the assignment record."""
        # Handle nested updates for questions and classroom_links
        if "questions" in updates:
            updates["questions"] = [
                asdict(q) if isinstance(q, campus.model.Question) else q
                for q in updates["questions"]
            ]
        if "classroom_links" in updates:
            updates["classroom_links"] = [
                asdict(l) if isinstance(l, campus.model.ClassroomLink) else l
                for l in updates["classroom_links"]
            ]

        try:
            assignment_storage.update_by_id(self.assignment_id, updates)
        except campus.storage.errors.NoChangesAppliedError:
            return None
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Assignment not found",
                id=self.assignment_id
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    def delete(self) -> None:
        """Delete the assignment."""
        try:
            # Verify assignment exists before deleting
            record = assignment_storage.get_by_id(self.assignment_id)
            if record is None:
                raise api_errors.ConflictError(
                    "Assignment not found",
                    id=self.assignment_id
                )
            assignment_storage.delete_by_id(self.assignment_id)
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Assignment not found",
                id=self.assignment_id
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
