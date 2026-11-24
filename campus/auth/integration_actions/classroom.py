"""Minimal Google Classroom REST caller for action proxies (#1221).

Runs on a released user credential strictly in-process (campus#1221
custody decision: provider tokens never cross a service boundary) —
only the allowlisted proxy verbs are implemented, and error responses
surface as typed campus errors with the upstream status attached
(never raw Google error bodies, never token material).
"""

import requests

from campus.common.errors import api_errors

BASE_URL = "https://classroom.googleapis.com/v1"
TIMEOUT = 10  # seconds; matches the webauth OAuth scheme's budget

# Google error `status` values the proxy routes give verb-specific
# meaning to (e.g. reclaim's FAILED_PRECONDITION = nothing to reclaim).
FAILED_PRECONDITION = "FAILED_PRECONDITION"


def _request(
        method: str,
        path: str,
        *,
        access_token: str,
        params: dict | None = None,
        json: dict | None = None,
) -> dict:
    """One authenticated Classroom REST call, errors typed.

    404 -> NotFoundError, 403 -> ForbiddenError, 429/5xx ->
    TemporarilyUnavailableError, other 4xx -> InvalidRequestError; all
    carry `upstream_status` and the Google error `status` string in
    details so verb semantics (FAILED_PRECONDITION) stay decidable at
    the route layer. Transport failures are 503-shaped.
    """
    try:
        response = requests.request(
            method,
            BASE_URL + path,
            params=params,
            json=json,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=TIMEOUT,
        )
    except requests.RequestException as err:
        raise api_errors.TemporarilyUnavailableError(
            f"Classroom API unreachable: {err}"
        ) from err

    body: dict = {}
    if response.content:
        body = response.json()
    if response.status_code >= 400:
        google_error = body.get("error") or {}
        message = google_error.get("message") or response.reason
        details = {
            "upstream_status": response.status_code,
            "google_status": google_error.get("status", ""),
        }
        if response.status_code == 404:
            raise api_errors.NotFoundError(message, **details)
        if response.status_code == 403:
            raise api_errors.ForbiddenError(message, **details)
        if response.status_code == 429 or response.status_code >= 500:
            raise api_errors.TemporarilyUnavailableError(message, **details)
        raise api_errors.InvalidRequestError(message, **details)
    return body


def list_student_submissions(
        course_id: str, coursework_id: str, *, access_token: str
) -> list[dict]:
    """The caller's (userId=me) studentSubmissions for a CourseWork.

    The released credential IS the target student's, so `userId=me`
    resolves their own row without needing their Classroom email.
    """
    body = _request(
        "GET",
        f"/courses/{course_id}/courseWork/{coursework_id}/studentSubmissions",
        params={"userId": "me"},
        access_token=access_token,
    )
    return body.get("studentSubmissions", [])


def turn_in(
        course_id: str, coursework_id: str, submission_id: str,
        *, access_token: str,
) -> dict:
    """Turn in the student submission (scope: coursework.me)."""
    return _request(
        "POST",
        f"/courses/{course_id}/courseWork/{coursework_id}"
        f"/studentSubmissions/{submission_id}:turnIn",
        json={},
        access_token=access_token,
    )


def reclaim(
        course_id: str, coursework_id: str, submission_id: str,
        *, access_token: str,
) -> dict:
    """Reclaim a turned-in submission (scope: coursework.me)."""
    return _request(
        "POST",
        f"/courses/{course_id}/courseWork/{coursework_id}"
        f"/studentSubmissions/{submission_id}:reclaim",
        json={},
        access_token=access_token,
    )


def modify_attachments(
        course_id: str, coursework_id: str, submission_id: str,
        attachments: list[dict], *, access_token: str,
) -> dict:
    """Add link attachments to a submission (scope: coursework.me)."""
    return _request(
        "POST",
        f"/courses/{course_id}/courseWork/{coursework_id}"
        f"/studentSubmissions/{submission_id}:modifyAttachments",
        json={"addAttachments": attachments},
        access_token=access_token,
    )


def get_student_submission(
        course_id: str, coursework_id: str, submission_id: str,
        *, access_token: str,
) -> dict:
    """Read one student submission (scope: coursework.me)."""
    return _request(
        "GET",
        f"/courses/{course_id}/courseWork/{coursework_id}"
        f"/studentSubmissions/{submission_id}",
        access_token=access_token,
    )
