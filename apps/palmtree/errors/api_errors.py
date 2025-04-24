from .base import APIError, ErrorConstant, JsonDict

class InvalidRequestError(APIError):
    """Invalid request error.

    This error is raised when the request is invalid.
    """
    status_code: int = 400

    def __init__(
            self,
            message: str = "Invalid request",
            error_code: str = ErrorConstant.INVALID_REQUEST,
            **details
    ) -> None:
        super().__init__(message, error_code, **details)

