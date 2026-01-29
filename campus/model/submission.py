"""campus.model.submission

Submission model for Campus API.
"""

from dataclasses import dataclass, field

from campus.common import schema
from campus.common.utils import uid

from .base import Model


@dataclass(eq=False, kw_only=True)
class Response:
    """A student's response to a single question."""
    question_id: str  # References Assignment.question.id
    response_text: str


@dataclass(eq=False, kw_only=True)
class Feedback:
    """Teacher feedback on a specific question response."""
    question_id: str
    feedback_text: str
    teacher_id: schema.UserID
    created_at: schema.DateTime = field(default_factory=schema.DateTime.utcnow)


@dataclass(eq=False, kw_only=True)
class Submission(Model):
    """Dataclass representation of a student submission."""
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("submission", length=8)
    ))
    # created_at inherited from Model
    assignment_id: schema.CampusID
    student_id: schema.UserID
    course_id: str  # Google Classroom course ID (for querying)
    responses: list[Response] = field(default_factory=list)
    feedback: list[Feedback] = field(default_factory=list)
    submitted_at: schema.DateTime | None = None
    updated_at: schema.DateTime = field(
        default_factory=schema.DateTime.utcnow,
        metadata={"mutable": True}
    )

    @classmethod
    def from_resource(cls, resource: dict) -> "Submission":
        """Create a Submission from an API resource response.

        Handles nested deserialization of responses and feedback.
        """
        from dataclasses import asdict

        # Deserialize nested objects
        responses = [
            Response(**r) if isinstance(r, dict) else r
            for r in resource.get("responses", [])
        ]
        feedback = [
            Feedback(**f) if isinstance(f, dict) else f
            for f in resource.get("feedback", [])
        ]

        # Build kwargs for Submission constructor
        kwargs = {
            "id": resource["id"],
            "created_at": resource["created_at"],
            "assignment_id": resource["assignment_id"],
            "student_id": resource["student_id"],
            "course_id": resource["course_id"],
            "responses": responses,
            "feedback": feedback,
            "submitted_at": resource.get("submitted_at"),
            "updated_at": resource["updated_at"],
        }
        return cls(**kwargs)

    def to_resource(self) -> dict:
        """Convert the Submission to an API resource response.

        Handles nested serialization of responses and feedback.
        """
        from dataclasses import asdict

        return {
            "id": self.id,
            "created_at": self.created_at,
            "assignment_id": self.assignment_id,
            "student_id": self.student_id,
            "course_id": self.course_id,
            "responses": [asdict(r) for r in self.responses],
            "feedback": [asdict(f) for f in self.feedback],
            "submitted_at": self.submitted_at,
            "updated_at": self.updated_at,
        }

    def to_storage(self) -> dict:
        """Convert the Submission to storage format.

        Handles serialization of nested dataclasses to dicts.
        """
        from dataclasses import asdict

        data = super().to_storage()
        # Convert nested dataclasses to dicts for storage
        data['responses'] = [asdict(r) for r in self.responses]
        data['feedback'] = [asdict(f) for f in self.feedback]
        return data
