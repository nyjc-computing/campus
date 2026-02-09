# REST API Error Handling Specification

## 1. Scope

This document defines the **required behavior and response format** for all error responses returned by the API.

This specification applies to:

* All REST endpoints
* All HTTP methods
* All environments (dev, staging, prod), with environment-specific logging handled server-side

---

## 2. Error Signaling Rules

### 2.1 Primary Error Signal

* **HTTP status code is the authoritative signal of success or failure**
* APIs MUST NOT return `200 OK` for failed operations

### 2.2 Status Code Semantics

#### Client Errors (4xx)

| Status | Meaning              | Usage                                                     |
| ------ | -------------------- | --------------------------------------------------------- |
| 400    | Bad Request          | Malformed request, invalid JSON, basic validation failure |
| 401    | Unauthorized         | Missing or invalid authentication                         |
| 403    | Forbidden            | Authenticated but lacking permission                      |
| 404    | Not Found            | Resource does not exist or is not visible                 |
| 409    | Conflict             | Resource state conflict (duplicates, version mismatch)    |
| 422    | Unprocessable Entity | Domain or semantic validation failure                     |
| 429    | Too Many Requests    | Rate limiting                                             |

#### Server Errors (5xx)

| Status | Meaning               | Usage                        |
| ------ | --------------------- | ---------------------------- |
| 500    | Internal Server Error | Unhandled server failure     |
| 502    | Bad Gateway           | Upstream dependency failure  |
| 503    | Service Unavailable   | Temporary outage or overload |
| 504    | Gateway Timeout       | Upstream timeout             |

---

## 3. Error Response Envelope

### 3.1 Required Response Shape

All error responses MUST conform to the following structure:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable explanation",
    "details": {},
    "request_id": "string"
  }
}
```

### 3.2 Field Definitions

| Field        | Required    | Description                                   |
| ------------ | ----------- | --------------------------------------------- |
| `error`      | Yes         | Root error object                             |
| `code`       | Yes         | Stable, machine-readable error identifier     |
| `message`    | Yes         | Human-readable, UI-safe message               |
| `details`    | No          | Structured, domain-specific metadata          |
| `request_id` | Optional*   | Correlation ID for debugging                  |

> **\*** `request_id` is currently returned as `null`. Request correlation will be implemented in a future update.

---

## 4. Error Codes

### 4.1 General Rules

* Error codes MUST be:

  * `UPPER_SNAKE_CASE`
  * Stable across versions
  * Documented
* Error codes MUST NOT:

  * Encode numeric values
  * Depend on message text
  * Leak internal implementation details

### 4.2 Examples

```json
"code": "INVALID_EMAIL"
"code": "RESOURCE_ALREADY_EXISTS"
"code": "AUTH_TOKEN_EXPIRED"
"code": "PERMISSION_DENIED"
```

---

## 5. Validation Errors

### 5.1 Validation Error Status

* Validation failures MUST return:

  * **400 Bad Request** or **422 Unprocessable Entity**
* The chosen status MUST be used consistently across the API

### 5.2 Validation Error Format

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "One or more fields are invalid",
    "errors": [
      {
        "field": "email",
        "code": "INVALID_FORMAT",
        "message": "Email must be a valid address"
      },
      {
        "field": "password",
        "code": "TOO_SHORT",
        "message": "Password must be at least 12 characters"
      }
    ],
    "request_id": null
  }
}
```

> **Note:** `request_id` will contain a correlation ID once request tracing is implemented. Until then, it will be `null`.

### 5.3 Validation Error Rules

* `errors` MUST be an array
* Each entry MUST include:

  * `field`
  * `code`
  * `message`
* Clients MUST NOT infer meaning from message text

---

## 6. Internal Error Handling

### 6.1 Client-Facing Behavior

For internal failures:

* Messages MUST be generic
* No stack traces, SQL errors, or internal IDs may be exposed

```json
{
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "An unexpected error occurred",
    "request_id": null
  }
}
```

### 6.2 Server-Side Requirements

* Full error details MUST be logged internally
* `request_id` MUST correlate logs to responses (when implemented)
* **Development mode MAY include** `traceback`, `sql_errors`, and internal IDs in `details` for debugging
* **Production mode MUST NOT** expose `traceback`, `sql_errors`, or internal IDs in the response

---

## 7. Consistency Requirements

The API MUST ensure:

* Identical error shapes across all endpoints
* Identical semantics for the same HTTP status codes
* Identical casing and field naming everywhere

Any deviation is considered a contract violation.

---

## 8. Optional Standards Alignment

The API MAY align with an external specification, provided:

* The response remains semantically equivalent to this document

Accepted standards:

* RFC 7807 (Problem Details for HTTP APIs)
* JSON:API Error Object
* Custom OpenAPI-defined schema

---

## 9. Non-Goals

This specification explicitly does NOT cover:

* Localization strategy
* Logging format
* Retry semantics
* Client-side rendering behavior

---

## 10. Compliance Checklist (Agent-Usable)

An implementation is compliant if and only if:

* [ ] All failures return non-2xx status codes
* [ ] All error responses include `error.code` and `error.message`
* [ ] Error codes are stable and documented
* [ ] Validation errors return structured field-level data
* [ ] Internal errors do not leak internals
* [ ] Error format is identical across all endpoints
