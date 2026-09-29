name: Bug report
description: Something isn't working
labels: ["bug"]
body:
  - type: textarea
    id: description
    attributes:
      label: Description
      description: A clear, concise description of the bug.
    validations:
      required: true
  - type: textarea
    id: repro
    attributes:
      label: Steps to reproduce
      description: |
        The exact command(s) or request(s) to reproduce, against a named
        environment (local suite, Railway dev, etc.). A repro we can paste
        and run gets fixed much faster than a prose description.
      placeholder: |
        curl -s https://campusapi-development.up.railway.app/api/v1/circles/ \
          -H "Authorization: Bearer not-a-real-token"
        # or: .venv/Scripts/python.exe tests/run_tests.py contract
    validations:
      required: true
  - type: textarea
    id: expected
    attributes:
      label: Expected behavior
    validations:
      required: true
  - type: textarea
    id: actual
    attributes:
      label: Actual behavior
      description: Include the observed status code and the error envelope (code/message), not just "it fails".
    validations:
      required: true
  - type: input
    id: verified
    attributes:
      label: Last verified against
      description: Branch/commit and date this repro was last confirmed (so future triage knows whether it is stale).
      placeholder: "weekly @ 97ad7d0, 2026-09-29"
  - type: textarea
    id: logs
    attributes:
      label: Relevant logs
      description: Optional. Excerpt of the error response body or handler traceback.
