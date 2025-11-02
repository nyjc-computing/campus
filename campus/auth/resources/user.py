"""campus.auth.user

Implements Campus API for user access.
"""

import typing
from campus.common import schema
from campus.common.errors import api_errors
import campus.model
import campus.storage

user_storage = campus.storage.get_table("users")


def _from_record(
        record: dict[str, typing.Any],
) -> campus.model.User:
    """Convert a storage record to a User model instance."""
    return campus.model.User(
        id=schema.UserID(record['id']),
        created_at=schema.DateTime(record['created_at']),
        email=record['email'],
        name=record['name'],
        activated_at=(schema.DateTime(record['activated_at'])
                      if record['activated_at'] is not None
                      else None)
    )


def init_storage() -> None:
    """Initialize storage for user authentication."""
    user_storage.init_from_model("users", campus.model.User)


def activate(user_id: schema.UserID) -> None:
    """Activate a user account.

    Args:
        user_id: The user identifier
    """
    user = get(user_id)
    if user.activated_at:
        raise api_errors.InvalidRequestError(
            "Account already activated",
            user_id=user_id
        )
    user_storage.update_by_id(
        user_id,
        {"activated_at": schema.DateTime.utcnow()}
    )

def delete(user_id: schema.UserID) -> None:
    """Delete a user by ID.

    Args:
        user_id: The user ID
    """
    user_storage.delete_by_id(user_id)

def get(user_id: schema.UserID) -> campus.model.User:
    """Get a user by ID.

    Args:
        user_id: The user ID

    Returns:
        User instance
    """
    record = user_storage.get_by_id(user_id)
    if not record:
        raise api_errors.NotFoundError(
            f"User '{user_id}' not found",
            user_id=user_id
        )
    return _from_record(record=record)


def new(**kwargs: typing.Any) -> campus.model.User:
    """Create a new Campus user.

    Args:
        **kwargs: Additional fields for user creation

    Returns:
        User instance
    """
    user = _from_record(kwargs)
    user_storage.insert_one(user.to_storage())
    return user


def update(user_id: schema.UserID, **updates: typing.Any) -> None:
    """Update a Campus user's information.

    Args:
        user_id: The user identifier
        **updates: Fields to update

    Raises:
        NotFoundError: If user not found
    """
    campus.model.User.validate_update(updates)
    user_storage.update_by_id(user_id, updates)


class UsersResource:
    """Represents the users resource in Campus API Schema."""

    def __getitem__(self, user_id: schema.UserID) -> "UserResource":
        """Get a user record by user ID.

        Args:
            user_id: The user ID

        Returns:
            UserResource instance
        """
        return UserResource(user_id)

    def new(self, **kwargs: typing.Any) -> campus.model.User:
        """Create a new user and return it.

        Args:
            **kwargs: Additional fields for user creation

        Returns:
            User instance
        """
        return new(**kwargs)


class UserResource:
    """Represents a single user in Campus API Schema."""

    def __init__(self, user_id: schema.UserID):
        self._user_id = user_id

    def activate(self) -> None:
        """Activate the user account."""
        activate(self._user_id)

    def delete(self) -> None:
        """Delete the user record."""
        delete(self._user_id)

    def get(self) -> campus.model.User:
        """Get the user record.

        Returns:
            User instance
        """
        return get(self._user_id)

    def update(self, **updates: typing.Any) -> None:
        """Update the user record.

        Args:
            **updates: Fields to update (email, name)
        """
        update(self._user_id, **updates)
