"""campus.auth.user

Implements Campus API for user access.
"""

import typing
from campus.common import schema
from campus.common.errors import api_errors
import campus.model as model
import campus.storage

user_storage = campus.storage.get_table("users")


def _from_record(
        record: dict[str, typing.Any],
) -> model.User:
    """Convert a storage record to a User model instance."""
    return model.User(
        id=schema.UserID(record['id']),
        created_at=schema.DateTime(record['created_at']),
        email=record['email'],
        name=record['name'],
        activated_at=(schema.DateTime(record['activated_at'])
                      if record['activated_at'] is not None
                      else None)
    )


class UsersResource:
    """Represents the users resource in Campus API Schema."""

    @staticmethod
    def init_storage() -> None:
        """Initialize storage for user authentication."""
        user_storage.init_from_model("users", model.User)

    def __getitem__(self, user_id: schema.UserID) -> "UserResource":
        """Get a user record by user ID.

        Args:
            user_id: The user ID

        Returns:
            UserResource instance
        """
        return UserResource(user_id)

    def list(self) -> list[model.User]:
        """Get all users.

        Returns:
            List of User instances
        """
        records = user_storage.get_matching({})
        return [_from_record(record) for record in records]

    def new(
            self,
            email: schema.Email,
            name: str,
            activated_at: schema.DateTime | None = None,
    ) -> model.User:
        """Create a new Campus user.

        Args:
            email: User's email address (used as user_id)
            name: User's display name
            activated_at: Optional activation timestamp

        Returns:
            User instance
        """
        # Create user record with email as id
        record = {
            "id": schema.UserID(email),
            "email": email,
            "name": name,
            "created_at": schema.DateTime.utcnow(),
            "activated_at": activated_at,
        }
        user = _from_record(record)
        user_storage.insert_one(user.to_storage())
        return user

    def get_or_create(
            self,
            email: schema.Email,
            name: str,
    ) -> model.User:
        """Get a user by email, creating them if they don't exist.

        This is the primary method for user auto-provisioning during
        OAuth login flows.

        Args:
            email: User's email address (used as user_id)
            name: User's display name

        Returns:
            User instance (either existing or newly created)
        """
        user_id = schema.UserID(email)
        try:
            return self[user_id].get()
        except api_errors.NotFoundError:
            return self.new(email=email, name=name)


class UserResource:
    """Represents a single user in Campus API Schema."""

    def __init__(self, user_id: schema.UserID):
        self.user_id = user_id

    def activate(self) -> None:
        """Activate a user account.

        Args:
            user_id: The user identifier
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

        Args:
            user_id: The user ID
        """
        user_storage.delete_by_id(self.user_id)

    def get(self) -> model.User:
        """Get a user by ID.

        Args:
            user_id: The user ID

        Returns:
            User instance

        Raises:
            api_errors.NotFoundError: If user not found
        """
        try:
            record = user_storage.get_by_id(self.user_id)
        except campus.storage.errors.NotFoundError:
            raise api_errors.NotFoundError(
                f"User '{self.user_id}' not found",
                user_id=self.user_id
            )
        return _from_record(record=record)

    def update(self, **updates: typing.Any) -> None:
        """Update a Campus user's information.

        Args:
            user_id: The user identifier
            **updates: Fields to update

        Raises:
            NotFoundError: If user not found
        """
        model.User.validate_update(updates)
        user_storage.update_by_id(self.user_id, updates)
