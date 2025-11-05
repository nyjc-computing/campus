"""campus.api.resources.user

Implements Campus API for user access.
"""

import typing

from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import uid
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
                      if record.get('activated_at') is not None
                      else None)
    )


class UsersResource:
    """Represents the users resource in Campus API Schema."""

    @staticmethod
    def init_storage() -> None:
        """Initialize storage for user management."""
        user_storage.init_from_model("users", campus.model.User)

    def __getitem__(self, user_id: schema.UserID) -> "UserResource":
        """Get a user record by user ID.

        Args:
            user_id: The user ID

        Returns:
            UserResource instance
        """
        return UserResource(user_id)

    def list(self) -> list[campus.model.User]:
        """Get all users.

        Returns:
            List of User instances
        """
        records = user_storage.get_matching({})
        return [_from_record(record) for record in records]

    def new(self, **kwargs: typing.Any) -> campus.model.User:
        """Create a new Campus user.

        Args:
            **kwargs: Fields for user creation (email, name)

        Returns:
            User instance

        Raises:
            ConflictError: If user already exists
        """
        user_id = schema.UserID(uid.generate_user_uid(kwargs['email']))
        user = campus.model.User(
            id=user_id,
            created_at=schema.DateTime.utcnow(),
            email=kwargs['email'],
            name=kwargs['name'],
            activated_at=None
        )
        try:
            user_storage.insert_one(user.to_storage())
        except campus.storage.errors.ConflictError:
            raise api_errors.ConflictError(
                f"User with email '{kwargs['email']}' already exists",
                user_id=user_id
            ) from None
        return user


class UserResource:
    """Represents a single user in Campus API Schema."""

    def __init__(self, user_id: schema.UserID):
        self.user_id = user_id

    def activate(self) -> None:
        """Activate a user account.

        Raises:
            InvalidRequestError: If account is already activated
            NotFoundError: If user not found
        """
        user = self.get()
        if user.activated_at:
            raise api_errors.InvalidRequestError(
                "Account already activated",
                user_id=self.user_id
            )
        user_storage.update_by_id(
            self.user_id,
            {"activated_at": schema.DateTime.utcnow()}
        )

    def delete(self) -> None:
        """Delete a user by ID.

        Raises:
            NotFoundError: If user not found
        """
        try:
            user_storage.delete_by_id(self.user_id)
        except campus.storage.errors.NotFoundError:
            raise api_errors.NotFoundError(
                f"User '{self.user_id}' not found",
                user_id=self.user_id
            ) from None

    def get(self) -> campus.model.User:
        """Get a user by ID.

        Returns:
            User instance

        Raises:
            NotFoundError: If user not found
        """
        record = user_storage.get_by_id(self.user_id)
        if not record:
            raise api_errors.NotFoundError(
                f"User '{self.user_id}' not found",
                user_id=self.user_id
            )
        return _from_record(record=record)

    def update(self, **updates: typing.Any) -> None:
        """Update a Campus user's information.

        Args:
            **updates: Fields to update

        Raises:
            NotFoundError: If user not found
        """
        campus.model.User.validate_update(updates)
        try:
            user_storage.update_by_id(self.user_id, updates)
        except campus.storage.errors.NotFoundError:
            raise api_errors.NotFoundError(
                f"User '{self.user_id}' not found",
                user_id=self.user_id
            ) from None
