# Implementation Plan: Assignments Resource

**Issue:** [#309](https://github.com/nyjc-computing/campus/issues/309)
**Branch:** `nycomp/issue309`
**Status:** Planning

---

## Overview

Add an **Assignments** resource to Campus API for storing structured question-based assignments. This is needed for campus-classroom (Google Classroom Add-On).

## Key Design Decisions

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Storage Backend | PostgreSQL (tables) | Structured data, JSONB for questions/links |
| Question IDs | Hierarchical dot notation (q1, q1.a, q1.a.i) | Self-describing hierarchy |
| Assignment ID | `assignment_xxxxxxxx` | Full category name for clarity |
| Deadline Handling | Not stored in Campus | Managed by Google Classroom only (MVP) |

---

## Reference Implementation Patterns

Based on existing `circles` resource:

- **Model** → **Resource** → **Routes** separation
- Resources use `campus.storage.get_collection()` for MongoDB-style access
- Routes use `@flask_campus.unpack_request` for parameter unpacking
- Error handling via `campus.common.errors.api_errors`
- Yapper events for audit trails

---

## Implementation Checklist

### Phase 1: Model Layer

#### 1.1 Create `campus/model/assignment.py`

**File:** `campus/model/assignment.py`

```python
"""campus.model.assignment

Assignment model for Campus API.
"""

from dataclasses import dataclass, field

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
    """Link to a Google Classroom assignment."""
    course_id: str
    coursework_id: str
    attachment_id: str | None = None
    linked_at: schema.DateTime = field(default_factory=schema.DateTime.utcnow)


@dataclass(eq=False, kw_only=True)
class Assignment(Model):
    """Dataclass representation of an assignment record.

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
    classroom_links: list[ClassroomLink] = field(default_factory=list)

    def get_question_tree(self) -> dict:
        """Return questions as a nested tree structure."""
        tree: dict = {}
        for q in self.questions:
            node = {
                "id": q.id,
                "prompt": q.prompt,
                "question": q.question,
                "children": []
            }
            if q.level == 1:
                tree[q.id] = node
            elif q.parent_id in tree:
                tree[q.parent_id]["children"].append(node)
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
```

**Update** `campus/model/__init__.py`:
```python
from .assignment import Assignment, Question, ClassroomLink
```

---

### Phase 2: PostgreSQL Migration

#### 2.1 Create migration file

**File:** `campus/migrations/versions/001_add_assignments_table.py`

```python
"""Add assignments table.

Revision ID: 001
Create Date: 2025-01-28
"""
from campus.storage.tables.backend.postgres import PostgreSQLTable

def upgrade():
    """Create assignments table."""
    sql = """
    CREATE TABLE IF NOT EXISTS "assignments" (
        "id" TEXT PRIMARY KEY,
        "created_at" TIMESTAMP NOT NULL,
        "title" TEXT NOT NULL,
        "description" TEXT NOT NULL DEFAULT '',
        "questions" JSONB NOT NULL DEFAULT '[]',
        "created_by" TEXT NOT NULL,
        "updated_at" TIMESTAMP NOT NULL,
        "classroom_links" JSONB NOT NULL DEFAULT '[]'
    );

    CREATE INDEX idx_assignments_created_by ON "assignments"("created_by");
    CREATE INDEX idx_assignments_questions ON "assignments" USING GIN("questions");
    CREATE INDEX idx_assignments_classroom_links ON "assignments" USING GIN("classroom_links");
    """

    table = PostgreSQLTable("assignments")
    table.init_from_schema(sql)

def downgrade():
    """Drop assignments table."""
    sql = "DROP TABLE IF EXISTS \"assignments\";"
    table = PostgreSQLTable("assignments")
    table.init_from_schema(sql)
```

---

### Phase 3: Resource Layer

#### 3.1 Create `campus/api/resources/assignment.py`

**File:** `campus/api/resources/assignment.py`

```python
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
            assignment_storage.delete_by_id(self.assignment_id)
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Assignment not found",
                id=self.assignment_id
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
```

**Update** `campus/api/resources/__init__.py`:
```python
__all__ = [
    "circle",
    "emailotp",
    "assignment",  # Add this
]

from .circle import CirclesResource
from .emailotp import EmailOTPResource
from .assignment import AssignmentsResource  # Add this

# Initialize resource instances
circle = CirclesResource()
emailotp = EmailOTPResource()
assignment = AssignmentsResource()  # Add this
```

---

### Phase 4: Routes Layer

#### 4.1 Create `campus/api/routes/assignments.py`

**File:** `campus/api/routes/assignments.py`

```python
"""campus.api.routes.assignments

API routes for the assignments resource.
"""

import campus_python
import flask

import campus.model
import campus.yapper
from campus import flask_campus
from campus.common import schema
from campus.common.errors import api_errors

from .. import resources

bp = flask.Blueprint('assignments', __name__, url_prefix='/assignments')
yapper = campus.yapper.create()


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise assignment routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.get('/')
@flask_campus.unpack_request
def list_assignments(created_by: str | None = None) -> flask_campus.JsonResponse:
    """Summary:
        List all assignments matching filter requirements.

    Method:
        GET /assignments

    Query Parameters:
        created_by: str (optional)
            Filter by teacher who created the assignment

    Responses:
        200 OK: dict
            {"data": [assignment resources]}
    """
    filters = {}
    if created_by:
        filters['created_by'] = created_by

    result = resources.assignment.list(**filters)
    return {"data": [assignment.to_resource() for assignment in result]}, 200


@bp.post('/')
@flask_campus.unpack_request
def create_assignment(
    title: str,
    description: str = "",
    questions: list[dict] | None = None,
    classroom_links: list[dict] | None = None,
) -> flask_campus.JsonResponse:
    """Summary:
        Create a new assignment.

    Method:
        POST /assignments

    Request Body:
        title: str (required)
        description: str (optional)
        questions: list[dict] (optional)
        classroom_links: list[dict] (optional)

    Responses:
        201 Created: dict
            Assignment resource
    """
    # Get created_by from authenticated user
    created_by = flask.g.get('current_user', {}).get('id', 'unknown')

    assignment = resources.assignment.new(
        title=title,
        description=description,
        questions=questions or [],
        created_by=created_by,
        classroom_links=classroom_links or []
    )
    resource = assignment.to_resource()
    yapper.emit('campus.assignments.create', {'assignment_id': assignment.id})
    return resource, 201


@bp.get('/<string:assignment_id>')
def get_assignment(assignment_id: str) -> flask_campus.JsonResponse:
    """Summary:
        Get a single assignment by ID.

    Method:
        GET /assignments/{assignment_id}

    Responses:
        200 OK: dict
            Assignment resource
    """
    assignment = resources.assignment[schema.CampusID(assignment_id)].get()
    return assignment.to_resource(), 200


@bp.patch('/<string:assignment_id>')
@flask_campus.unpack_request
def update_assignment(
    *,
    assignment_id: str,
    title: str | None = None,
    description: str | None = None,
    questions: list[dict] | None = None,
    classroom_links: list[dict] | None = None,
) -> flask_campus.JsonResponse:
    """Summary:
        Update an assignment.

    Method:
        PATCH /assignments/{assignment_id}

    Request Body:
        title, description, questions, or classroom_links (all optional)

    Responses:
        200 OK: dict
            Empty object on success
    """
    updates = {}
    if title is not None:
        updates["title"] = title
    if description is not None:
        updates["description"] = description
    if questions is not None:
        # Convert dict questions to Question models
        updates["questions"] = [
            campus.model.Question(**q) for q in questions
        ]
    if classroom_links is not None:
        # Convert dict links to ClassroomLink models
        updates["classroom_links"] = [
            campus.model.ClassroomLink(**l) for l in classroom_links
        ]

    if not updates:
        raise api_errors.InvalidRequestError("Empty request body")

    resources.assignment[schema.CampusID(assignment_id)].update(**updates)
    yapper.emit('campus.assignments.update', {"assignment_id": assignment_id})
    return {}, 200


@bp.delete('/<string:assignment_id>')
def delete_assignment(assignment_id: str) -> flask_campus.JsonResponse:
    """Summary:
        Delete an assignment.

    Method:
        DELETE /assignments/{assignment_id}

    Responses:
        200 OK: dict
            Empty object on success
    """
    resources.assignment[schema.CampusID(assignment_id)].delete()
    yapper.emit('campus.assignments.delete', {"assignment_id": assignment_id})
    return {}, 200


@bp.post('/<string:assignment_id>/links')
@flask_campus.unpack_request
def add_classroom_link(
    *,
    assignment_id: str,
    course_id: str,
    coursework_id: str,
    attachment_id: str | None = None,
) -> flask_campus.JsonResponse:
    """Summary:
        Add a Google Classroom link to an assignment.

    Method:
        POST /assignments/{assignment_id}/links

    Request Body:
        course_id: str (required)
        coursework_id: str (required)
        attachment_id: str (optional)

    Responses:
        200 OK: dict
            Empty object on success
    """
    assignment = resources.assignment[schema.CampusID(assignment_id)].get()
    new_link = campus.model.ClassroomLink(
        course_id=course_id,
        coursework_id=coursework_id,
        attachment_id=attachment_id
    )
    assignment.classroom_links.append(new_link)

    resources.assignment[schema.CampusID(assignment_id)].update(
        classroom_links=assignment.classroom_links
    )
    yapper.emit('campus.assignments.link', {"assignment_id": assignment_id})
    return {}, 200
```

#### 4.2 Register routes in `campus/api/__init__.py`

**Add to imports:**
```python
from . import routes
```

**Add to init_app() function:**
```python
def init_app(app: flask.Flask | flask.Blueprint) -> None:
    # ... existing code ...

    # Organise API routes under api blueprint
    bp = flask.Blueprint('api_v1', __name__, url_prefix='/api/v1')
    routes.circles.init_app(bp)
    routes.emailotp.init_app(bp)
    routes.assignments.init_app(bp)  # Add this line
```

---

## Testing Strategy

### Unit Tests

**File:** `campus/tests/unit/test_assignment_model.py`

```python
"""Unit tests for Assignment model."""

import pytest
from campus.model import Assignment, Question, ClassroomLink
from campus.common import schema

def test_question_hierarchy():
    """Test question ID parsing."""
    q1 = Question(id="q1", prompt="P", question="Q?")
    assert q1.level == 1
    assert q1.parent_id is None
    assert q1.root_id == "q1"

    q1a = Question(id="q1.a", prompt="", question="Q?")
    assert q1a.level == 2
    assert q1a.parent_id == "q1"
    assert q1a.root_id == "q1"

    q1ai = Question(id="q1.a.i", prompt="", question="Q?")
    assert q1ai.level == 3
    assert q1ai.parent_id == "q1.a"
    assert q1ai.root_id == "q1"

def test_assignment_creation():
    """Test Assignment model creation."""
    assignment = Assignment(
        id=schema.CampusID("assignment_test12345"),
        title="Test Assignment",
        description="A test",
        questions=[
            Question(id="q1", prompt="Read...", question="What?"),
            Question(id="q1.a", prompt="", question="Explain...")
        ],
        created_by="teacher@example.com"
    )
    assert assignment.title == "Test Assignment"
    assert len(assignment.questions) == 2
    assert assignment.get_question("q1.a") is not None

def test_question_tree():
    """Test get_question_tree method."""
    assignment = Assignment(
        id=schema.CampusID("assignment_test12345"),
        title="Test",
        created_by="teacher@example.com",
        questions=[
            Question(id="q1", prompt="P1", question="Q1?"),
            Question(id="q1.a", prompt="", question="Q1a?"),
            Question(id="q1.a.i", prompt="", question="Q1ai?"),
        ]
    )
    tree = assignment.get_question_tree()
    assert "q1" in tree
    assert len(tree["q1"]["children"]) == 1
```

### Integration Tests

**File:** `campus/tests/integration/test_assignment_api.py`

```python
"""Integration tests for Assignment API."""

import pytest
from campus import create_app

@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    return app

@pytest.fixture
def client(app):
    return app.test_client()

def test_create_assignment(client):
    """Test POST /assignments"""
    response = client.post('/api/v1/assignments', json={
        "title": "Test Assignment",
        "description": "Test description",
        "questions": [
            {"id": "q1", "prompt": "Read...", "question": "What?"}
        ]
    })
    assert response.status_code == 201
    data = response.get_json()
    assert data["title"] == "Test Assignment"

def test_list_assignments(client):
    """Test GET /assignments"""
    response = client.get('/api/v1/assignments')
    assert response.status_code == 200
    data = response.get_json()
    assert "data" in data

def test_get_assignment(client):
    """Test GET /assignments/{id}"""
    # First create an assignment
    create_response = client.post('/api/v1/assignments', json={
        "title": "Test",
        "questions": []
    })
    assignment_id = create_response.get_json()["id"]

    # Then get it
    response = client.get(f'/api/v1/assignments/{assignment_id}')
    assert response.status_code == 200
```

---

## Success Criteria

- [ ] All CRUD operations working via API
- [ ] PostgreSQL table created with correct schema
- [ ] Questions serialize/deserialize correctly to JSONB
- [ ] Classroom links stored and retrieved correctly
- [ ] Unit tests pass (coverage > 80%)
- [ ] Integration tests pass
- [ ] Yapper events emitted for all mutations
- [ ] Resource registered in `campus/api/resources/__init__.py`
- [ ] Routes registered in `campus/api/__init__.py`

---

## Open Questions

| # | Question | Decision |
|---|----------|----------|
| 1 | How to get `created_by` from auth context? | Use `flask.g.current_user` |
| 2 | Cascade delete when assignment deleted? | No action for MVP |
| 3 | Should we validate question ID format? | Add validation in model |
| 4 | How to handle JSONB serialization? | Test with PostgreSQL backend |
