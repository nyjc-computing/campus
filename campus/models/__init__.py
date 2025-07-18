"""campus.models

# Campus API Model

This module contains models for the Campus API server.

Each model encapsulates the logic for representing and manipulating Campus
resources.

## Principles

### Storage-agnostic

- Models should be storage-agnostic and should not depend on the underlying
  storage implementation.
- This means the schema for models should aim to use standard/common features
  of databases in general, and avoid database-specific features.

### Transparency

- The design of models should be intutitive and easy to understand.
- Some denormalisation is acceptable, to avoid excessive abstraction that
  obscures unnecessarily the underlying data model.

### Extensibility

- Where possible, the design of models should leave room for extensibility.
- This means that the design should not be too rigid, and should allow for
  future changes without requiring significant refactoring.
- It is worth leaving some performance on the table to keep the data model
  flexible.

### Avoid tight coupling
  
- Avoid tight coupling with frameworks.
- where it is easy to do so, use callbacks and hooks that allow behaviour to be
  specified or customised by users, unless this overly obscures the model logic.
- As much as possible, promote the use of decorators and other Pythonic patterns
  to allow users to extend the model behaviour.

## Conventions

### Consistent ID pattern

- For ease of lookup generalisation, all models must use a consistent ID
  pattern.
- The design of the ID patter should not depend on features of a specific
  database or database type.

### Mirror Campus API operations

- The naming conventions for model methods should mirror the Campus API
  operations and verbs.
- Model users should be able to intuit the method arguments, rquiring
  documentation only to confirm usage or understand nuances more clearly.

### Support native Python types

- Campus is not trying to be a macroframework; a user should not need to know
  an entire class hierarchy to implement a Campus server.
- Where annotation and encapsulation is desired, try to subclass or extend the
  behaviour of existing Python classes and APIs, in a way that does not obscure
  the logic of the model.
- However, low-level details should be delegated to util functions, for
  easier standardised handling of common tasks, e.g. datetime conversion and
  formatting.

### Typing conventions

- Request and response bodies should be typed using TypedDict.
- Where TypedDicts are an acceptable argument type, use Mapping[str, Any] or
  Mapping[str, JsonSerializable].
- Explicitly specify total=True or total=False for TypedDicts.
- Use NotRequired for record/resource fields that might not exist, or be None.
- When the project is updated to python>=3.13, use ReadOnly to indicate fields
  that should not be modified, e.g. `id`, `created_at`.

### Naming conventions

- Request and response body schemas should be suffixed with the verb they
  represent, e.g. `UserNew`, `UserUpdate`.
- Model schemas should be suffixed with `Resource`, e.g. `UserResource`.
- Models and schemas should be named in singular, e.g. `UserResource`, since
  they represent a single resource record.  
  This makes it easier to differentiate records and resources.

### Validation

- While parameter types are declared in the submodules of `models`, Models are
  not responsible for validating the types and formats of their arguments.
- That would involve importing many more modules, violating the Single
  Responsibility Principle.
- Model users should validate their arguments before passing them to the model.
- The model will generally rely on the backend to raise errors if input is
  invalid.
"""

from . import (
    circle,
    emailotp,
    user
)

__all__ = [
    "circle",
    "emailotp",
    "user"
]
