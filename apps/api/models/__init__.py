"""apps/api/models

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

### Avoid tight coupling
  
- Avoid tight coupling with frameworks.
- where it is easy to do so, use callbacks and hooks that allow behaviour to be
  specified or customised by users, unless this overly obscures the model logic.
- As much as possible, promote the use of decorators and other Pythonic patterns
  to allow users to extend the model behaviour.
"""
