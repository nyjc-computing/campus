"""campus.model.classroom

Classroom models for Campus Classroom (Google Classroom Add-On).

This module contains all models related to the campus-classroom feature:
- Assignments with structured questions
- Student submissions with responses
- Teacher feedback
- Google Classroom integration links

For schema details, see:
https://github.com/nyjc-computing/campus-classroom/blob/main/docs/schema-proposal.md
"""

from dataclasses import dataclass, field
import re

from campus.common import schema
from campus.common.utils import uid

from .base import Model


# ============================================================================
# Assignment Models
# ============================================================================

@dataclass(eq=False, kw_only=True)
class Question:
    """A single question within an assignment.

    Question IDs use hierarchical dot notation (q1, q1.a, q1.a.i).
    Hierarchy is self-describing in the ID - no parent_id needed.

    Level 1: q1, q2, q3, ... (main questions)
    Level 2: q1.a, q1.b, q1.c, ... (parts)
    Level 3: q1.a.i, q1.a.ii, q1.b.i, ... (subparts)
    Level 4+: q1.a.i.1, q1.a.i.2, ... (further nesting)
    """
    id: str  # e.g., "q1", "q1.a", "q1.a.i"
    prompt: str  # Context/passage (may be empty)
    question: str  # The actual question/task

    def __post_init__(self) -> None:
        """Validate question ID format."""
        # Validate hierarchical dot notation: alphanumeric with dots only
        if not re.match(r'^[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)*$', self.id):
            raise ValueError(
                f"Invalid question ID format: {self.id}. "
                "Must use hierarchical dot notation (e.g., q1, q1.a, q1.a.i)"
            )

    @property
    def level(self) -> int:
        """Return the hierarchy level (1-indexed)."""
        return len(self.id.split("."))

    @property
    def parent_id(self) -> str | None:
        """Return the parent question ID, or None for top-level questions."""
        parts = self.id.split(".")
        if len(parts) <= 1:
            return None
        return ".".join(parts[:-1])

    @property
    def root_id(self) -> str:
        """Return the root question ID (e.g., 'q1' for 'q1.a.ii')."""
        return self.id.split(".")[0]


@dataclass(eq=False, kw_only=True)
class ClassroomLink:
    """Link to a Google Classroom assignment.

    One assignment can be linked to multiple Classroom classes.
    Each link represents one CourseWork assignment in one course.
    """
    course_id: str  # Google Classroom course ID
    coursework_id: str  # Google Classroom assignment ID
    attachment_id: str | None = None  # Google Classroom attachment ID (if Add-On)
    linked_at: schema.DateTime = field(default_factory=schema.DateTime.utcnow)


@dataclass(eq=False, kw_only=True)
class Assignment(Model):
    """Dataclass representation of an assignment record.

    An assignment contains structured questions and can be linked
    to one or more Google Classroom classes.

    Note: Deadlines are managed by Google Classroom, not stored here.
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("assignment", length=8)
    ))
    # created_at inherited from Model
    title: str
    description: str = ""
    questions: list[Question] = field(default_factory=list)
    created_by: schema.UserID  # Teacher who created the assignment
    updated_at: schema.DateTime = field(
        default_factory=schema.DateTime.utcnow,
        metadata={"mutable": True}
    )
    # Links to Google Classroom (one-to-many)
    classroom_links: list[ClassroomLink] = field(default_factory=list)

    @classmethod
    def from_resource(cls, resource: dict) -> "Assignment":
        """Create an Assignment from an API resource response.

        Handles nested deserialization of questions and classroom_links.
        """
        # Deserialize nested objects
        questions = [
            Question(**q) if isinstance(q, dict) else q
            for q in resource.get("questions", [])
        ]
        classroom_links = [
            ClassroomLink(
                course_id=l["course_id"],
                coursework_id=l["coursework_id"],
                attachment_id=l.get("attachment_id"),
                **({"linked_at": schema.DateTime(l["linked_at"])} if "linked_at" in l else {})
            ) if isinstance(l, dict) else l
            for l in resource.get("classroom_links", [])
        ]

        # Build kwargs for Assignment constructor
        kwargs = {
            "id": resource["id"],
            "created_at": resource["created_at"],
            "title": resource["title"],
            "description": resource.get("description", ""),
            "questions": questions,
            "created_by": resource["created_by"],
            "updated_at": resource["updated_at"],
            "classroom_links": classroom_links,
        }
        return cls(**kwargs)

    def to_resource(self) -> dict:
        """Convert the Assignment to an API resource response.

        Handles nested serialization of questions and classroom_links.
        """
        from dataclasses import asdict
        return {
            "id": self.id,
            "created_at": self.created_at,
            "title": self.title,
            "description": self.description,
            "questions": [asdict(q) for q in self.questions],
            "created_by": self.created_by,
            "updated_at": self.updated_at,
            "classroom_links": [asdict(l) for l in self.classroom_links],
        }

    def to_storage(self) -> dict:
        """Convert the Assignment to storage format.

        Handles serialization of nested dataclasses to dicts.
        """
        from dataclasses import asdict

        data = super().to_storage()
        # Convert nested dataclasses to dicts for storage
        data['questions'] = [asdict(q) for q in self.questions]
        data['classroom_links'] = [asdict(l) for l in self.classroom_links]
        return data

    def get_question_tree(self) -> dict:
        """Return questions as a nested tree structure."""
        # First pass: create all nodes
        nodes = {}
        for q in self.questions:
            nodes[q.id] = {
                "id": q.id,
                "prompt": q.prompt,
                "question": q.question,
                "children": []
            }

        # Second pass: build tree structure
        tree: dict = {}
        for q in self.questions:
            node = nodes[q.id]
            if q.level == 1:
                tree[q.id] = node
            elif q.parent_id in nodes:
                nodes[q.parent_id]["children"].append(node)
        return tree

    def get_question(self, question_id: str) -> Question | None:
        """Get a question by ID."""
        for q in self.questions:
            if q.id == question_id:
                return q
        return None

    def get_questions_for_root(self, root_id: str) -> list[Question]:
        """Get all questions under a root question (including subparts)."""
        prefix = f"{root_id}."
        return [
            q for q in self.questions
            if q.id == root_id or q.id.startswith(prefix)
        ]


# ============================================================================
# Submission Models
# ============================================================================

@dataclass(eq=False, kw_only=True)
class Response:
    """A student's response to a single question.

    References Assignment.question.id via question_id.
    """
    question_id: str  # References Assignment.question.id
    response_text: str


@dataclass(eq=False, kw_only=True)
class Feedback:
    """Teacher feedback on a specific question response.

    Each question can have one feedback entry (replaces previous).
    """
    question_id: str  # References Response.question_id
    feedback_text: str
    teacher_id: schema.UserID
    created_at: schema.DateTime = field(default_factory=schema.DateTime.utcnow)


@dataclass(eq=False, kw_only=True)
class Submission(Model):
    """Dataclass representation of a student submission.

    A submission contains student responses to an assignment's questions,
    along with optional teacher feedback.

    Deadline enforcement: Check Classroom API for due date and lock
    editing when passed. For MVP, Google Classroom manages deadlines.
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("submission", length=8)
    ))
    # created_at inherited from Model
    assignment_id: schema.CampusID  # References Assignment.id
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

    def get_response(self, question_id: str) -> Response | None:
        """Get a response by question ID."""
        for r in self.responses:
            if r.question_id == question_id:
                return r
        return None

    def get_feedback(self, question_id: str) -> Feedback | None:
        """Get feedback for a specific question."""
        for f in self.feedback:
            if f.question_id == question_id:
                return f
        return None

    def is_submitted(self) -> bool:
        """Check if submission has been finalized."""
        return self.submitted_at is not None


__all__ = [
    "Assignment",
    "ClassroomLink",
    "Feedback",
    "Question",
    "Response",
    "Submission",
]
