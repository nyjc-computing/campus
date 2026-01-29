"""campus.api.resources.submission

Submission resource for Campus API.
"""

import typing
from dataclasses import asdict

from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import uid
import campus.model
import campus.storage

submission_storage = campus.storage.get_collection("submissions")


def _from_record(record: dict) -> campus.model.Submission:
    """Convert a storage record to a Submission model instance."""
    responses = [
        campus.model.Response(
            question_id=r["question_id"],
            response_text=r["response_text"]
        )
        for r in record.get("responses", [])
    ]

    feedback = [
        campus.model.Feedback(
            question_id=f["question_id"],
            feedback_text=f["feedback_text"],
            teacher_id=schema.UserID(f["teacher_id"]),
            created_at=schema.DateTime(f["created_at"])
        )
        for f in record.get("feedback", [])
    ]

    return campus.model.Submission(
        id=schema.CampusID(record['id']),
        created_at=schema.DateTime(record['created_at']),
        assignment_id=schema.CampusID(record['assignment_id']),
        student_id=schema.UserID(record['student_id']),
        course_id=record['course_id'],
        responses=responses,
        feedback=feedback,
        submitted_at=schema.DateTime(record['submitted_at']) if record.get(
            'submitted_at') else None,
        updated_at=schema.DateTime(record['updated_at'])
    )


class SubmissionsResource:
    """Represents the submissions resource in Campus API Schema."""

    @staticmethod
    def init_storage() -> None:
        """Initialize storage for submissions."""
        submission_storage.init_collection()

    def __getitem__(self, submission_id: schema.CampusID) -> "SubmissionResource":
        return SubmissionResource(submission_id)

    def list(self, **filters: typing.Any) -> list[campus.model.Submission]:
        """List all submissions matching filters."""
        try:
            records = submission_storage.get_matching(filters)
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        return [_from_record(record) for record in records]

    def new(self, **fields: typing.Any) -> campus.model.Submission:
        """Create a new submission."""
        submission = campus.model.Submission(
            id=schema.CampusID(
                uid.generate_category_uid("submission", length=8)
            ),
            created_at=schema.DateTime.utcnow(),
            assignment_id=schema.CampusID(fields["assignment_id"]),
            student_id=schema.UserID(fields["student_id"]),
            course_id=fields["course_id"],
            responses=[
                campus.model.Response(**r)
                for r in fields.get("responses", [])
            ],
            feedback=[
                campus.model.Feedback(**f)
                for f in fields.get("feedback", [])
            ],
            submitted_at=schema.DateTime(fields["submitted_at"]) if fields.get(
                "submitted_at") else None,
            updated_at=schema.DateTime.utcnow()
        )

        try:
            submission_storage.insert_one(submission.to_storage())
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

        return submission


class SubmissionResource:
    """Represents a single submission in Campus API Schema."""

    def __init__(self, submission_id: schema.CampusID):
        self.submission_id = submission_id

    def get(self) -> campus.model.Submission:
        """Get the submission record."""
        try:
            record = submission_storage.get_by_id(self.submission_id)
            if record is None:
                raise api_errors.ConflictError(
                    "Submission not found",
                    id=self.submission_id
                )
            return _from_record(record)
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Submission not found",
                id=self.submission_id
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    def update(self, **updates: typing.Any) -> None:
        """Update the submission record."""
        # Handle nested updates for responses and feedback
        if "responses" in updates:
            updates["responses"] = [
                asdict(r) if isinstance(r, campus.model.Response) else r
                for r in updates["responses"]
            ]
        if "feedback" in updates:
            updates["feedback"] = [
                asdict(f) if isinstance(f, campus.model.Feedback) else f
                for f in updates["feedback"]
            ]

        try:
            submission_storage.update_by_id(self.submission_id, updates)
        except campus.storage.errors.NoChangesAppliedError:
            return None
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Submission not found",
                id=self.submission_id
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    def delete(self) -> None:
        """Delete the submission."""
        try:
            # Verify submission exists before deleting
            record = submission_storage.get_by_id(self.submission_id)
            if record is None:
                raise api_errors.ConflictError(
                    "Submission not found",
                    id=self.submission_id
                )
            submission_storage.delete_by_id(self.submission_id)
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Submission not found",
                id=self.submission_id
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
