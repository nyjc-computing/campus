"""campus.auth.resources.device_code

Device code resource for OAuth 2.0 Device Authorization Flow.

This module manages device codes for CLI and other device authentication.
"""

import typing

from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import uid, secret
import campus,config as config
import campus.model as model
import campus.storage

device_code_storage = campus.storage.get_collection("device_codes")


def init_storage() -> None:
    """Initialize storage for device code resource."""
    device_code_storage.init_from_model(
        "device_codes", model.DeviceCode
    )


class DeviceCodeResource:
    """Represents the device code resource in Campus API Schema."""

    @staticmethod
    def init_storage() -> None:
        """Initialize storage for device code resource."""
        device_code_storage.init_from_model(
            "device_codes", model.DeviceCode
        )

    def create(
            self,
            *,
            client_id: schema.CampusID,
            scopes: list[str] | None = None,
    ) -> model.DeviceCode:
        """Create a new device code.

        Args:
            client_id: The OAuth client identifier
            scopes: Requested OAuth scopes

        Returns:
            DeviceCode instance
        """
        import logging
        logger = logging.getLogger(__name__)

        device_code_id = uid.generate_category_uid("device_code")
        device_code_str = secret.generate_device_code()
        user_code = secret.generate_user_code()

        device_code = _from_record({
            "id": device_code_id,
            "device_code": device_code_str,
            "user_code": user_code,
            "client_id": client_id,
            "scopes": scopes or [],
            "expiry_seconds": config.DEFAULT_DEVICE_CODE_EXPIRY_SECONDS,
            "interval": config.DEFAULT_DEVICE_CODE_POLL_INTERVAL,
            "state": "pending",
        })

        try:
            device_code_storage.insert_one(device_code.to_storage())
        except Exception as e:
            logger.error(f"[DEVICE_CODE] Failed to insert device code: {e}")
            raise api_errors.InternalError.from_exception(e)
        else:
            return device_code

    def get_by_device_code(
            self,
            device_code: str,
    ) -> model.DeviceCode:
        """Get a device code by device code string.

        Args:
            device_code: The device code string

        Returns:
            DeviceCode instance

        Raises:
            api_errors.NotFoundError: If device code not found
        """
        import logging
        logger = logging.getLogger(__name__)

        records = device_code_storage.get_matching({"device_code": device_code})
        if not records:
            logger.warning(f"[DEVICE_CODE] Device code not found: {device_code}")
            raise api_errors.NotFoundError(
                f"Device code not found or expired",
                device_code=device_code
            )

        device_code_obj = _from_record(records[0])

        # Check if expired
        if device_code_obj.is_expired():
            device_code_obj.expire()
            device_code_storage.update_by_id(
                device_code_obj.id,
                {"state": "expired"}
            )
            raise api_errors.InvalidRequestError(
                "The device code has expired. Please restart the authentication flow."
            )

        return device_code_obj

    def get_by_user_code(
            self,
            user_code: str,
    ) -> model.DeviceCode:
        """Get a device code by user code string.

        Args:
            user_code: The user code string

        Returns:
            DeviceCode instance

        Raises:
            api_errors.NotFoundError: If user code not found
        """
        import logging
        logger = logging.getLogger(__name__)

        records = device_code_storage.get_matching({"user_code": user_code})
        if not records:
            logger.warning(f"[DEVICE_CODE] User code not found: {user_code}")
            raise api_errors.NotFoundError(
                f"Invalid user code",
                user_code=user_code
            )

        device_code_obj = _from_record(records[0])

        # Check if expired
        if device_code_obj.is_expired():
            device_code_obj.expire()
            device_code_storage.update_by_id(
                device_code_obj.id,
                {"state": "expired"}
            )
            raise api_errors.NotFoundError(
                f"This user code has expired",
                user_code=user_code
            )

        return device_code_obj

    def update(
            self,
            device_code_id: schema.CampusID,
            **updates: typing.Any,
    ) -> model.DeviceCode:
        """Update a device code.

        Args:
            device_code_id: The device code ID
            **updates: Fields to update

        Returns:
            Updated DeviceCode instance
        """
        try:
            device_code_storage.update_by_id(device_code_id, updates)
        except campus.storage.errors.NotFoundError as e:
            raise api_errors.NotFoundError(
                "Device code not found",
                device_code_id=str(device_code_id)
            ) from e
        except Exception as e:
            raise api_errors.InternalError.from_exception(e) from e

        return self.get_by_id(device_code_id)

    def get_by_id(
            self,
            device_code_id: schema.CampusID,
    ) -> model.DeviceCode:
        """Get a device code by ID.

        Args:
            device_code_id: The device code ID

        Returns:
            DeviceCode instance

        Raises:
            api_errors.NotFoundError: If device code not found
        """
        record = device_code_storage.get_by_id(device_code_id)
        if not record:
            raise api_errors.NotFoundError(
                "Device code not found",
                device_code_id=str(device_code_id)
            )
        return _from_record(record)

    def delete(
            self,
            device_code_id: schema.CampusID,
    ) -> None:
        """Delete a device code.

        Args:
            device_code_id: The device code ID
        """
        try:
            device_code_storage.delete_by_id(device_code_id)
        except campus.storage.errors.NotFoundError:
            pass
        except Exception as e:
            raise api_errors.InternalError.from_exception(e)

    def sweep(
            self,
            *,
            at_time: schema.DateTime | None = None
    ) -> int:
        """Delete expired device codes from the database.

        Returns the number of deleted device codes.
        """
        expired_records = (
            model.DeviceCode.from_storage(r)
            for r in device_code_storage.get_matching({})
        )
        expired_codes = (
            dc for dc in expired_records if dc.is_expired(at_time=at_time)
        )
        deletion_count = 0
        for device_code in expired_codes:
            device_code_storage.delete_by_id(device_code.id)
            deletion_count += 1
        return deletion_count


def _from_record(
        record: dict[str, typing.Any],
) -> model.DeviceCode:
    """Convert a storage record to a DeviceCode model instance."""
    args: dict[str, typing.Any] = {}
    if "id" in record:
        args["id"] = schema.CampusID(record["id"])
    if "created_at" in record and record["created_at"] is not None:
        args["created_at"] = schema.DateTime(record["created_at"])
    if "expires_at" in record and record["expires_at"] is not None:
        args["expires_at"] = schema.DateTime(record["expires_at"])
    elif "expiry_seconds" in record and "expires_at" not in record:
        args["expires_at"] = schema.DateTime.utcafter(
            seconds=config.DEFAULT_DEVICE_CODE_EXPIRY_SECONDS
        )
    args["device_code"] = record["device_code"]
    args["user_code"] = record["user_code"]
    args["client_id"] = schema.CampusID(record["client_id"])
    if "user_id" in record and record["user_id"] is not None:
        args["user_id"] = schema.UserID(record["user_id"])
    if "scopes" in record:
        args["scopes"] = record["scopes"]
    if "interval" in record:
        args["interval"] = record["interval"]
    if "state" in record:
        args["state"] = record["state"]

    result = model.DeviceCode(**args)
    return result


# Singleton instance
device_code = DeviceCodeResource()
