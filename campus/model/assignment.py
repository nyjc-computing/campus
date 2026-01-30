"""campus.model.assignment

Assignment model for Campus API.
"""

from dataclasses import dataclass, field
import re

from campus.common import schema
from campus.common.utils import uid

from .base import Model


@dataclass(eq=False, kw_only=True)
class Question:
    """A single question within an assignment.

    Question IDs use hierarchical dot notation (q1, q1.a, q1.a.i).
    Hierarchy is self-describing in the ID.
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
        """Return the parent question ID, or None for top-level."""
        parts = self.id.split(".")
        if len(parts) <= 1:
            return None
        return ".".join(parts[:-1])

    @property
    def root_id(self) -> str:
        """Return the root question ID."""
        return self.id.split(".")[0]


@dataclass(eq=False, kw_only=True)
class ClassroomLink:
    """Link to a Google Classroom assignment.

    One assignment can be linked to multiple Classroom classes.
    """
    course_id: str
    coursework_id: str
    attachment_id: str | None = None
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
        from dataclasses import asdict

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
        """Get all questions under a root question."""
        prefix = f"{root_id}."
        return [
            q for q in self.questions
            if q.id == root_id or q.id.startswith(prefix)
        ]
