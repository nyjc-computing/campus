# Campus OAuth Error Handling Specification

**Applies to:** `campus.auth`
**Integrates with:** Campus REST API Error Handling Specification (Base Spec)

---

## 1. Scope and Intent

This document defines **OAuth-specific error handling rules** for the Campus platform.

It extends (but does not replace) the base error-handling specification used by `campus.api`.

Goals:

* Full OAuth 2.0 protocol compliance (RFC 6749, RFC 6750)
* Single, consistent error contract across Campus services
* No security leaks
* Deterministic, agent-friendly behavior

---

## 2. Inheritance from Base Spec

Unless explicitly overridden here, **all rules from the Campus REST API Error Handling Specification apply**.

In particular:

* HTTP status codes are authoritative
* Error responses use the same top-level `error` envelope
* Error codes are stable, machine-readable, and documented
* Internal details are never exposed to clients

---

## 3. OAuth Error Signaling Model

OAuth errors have **two parallel representations**:

1. **Canonical Campus Error**

   * `error.code` (internal, stable)
   * `error.message` (UI-safe)

2. **OAuth Protocol Error**

   * RFC-defined error string (e.g. `invalid_client`)
   * Returned via:

     * `details.oauth_error` (JSON responses)
     * OAuth redirect parameters
     * `WWW-Authenticate` header (when required)

Both MUST be present where applicable.

---

## 4. OAuth Error Response Envelope (JSON)

### 4.1 Required Shape

For non-redirect OAuth endpoints, error responses MUST use the standard Campus envelope:

```json
{
  "error": {
    "code": "AUTH_INVALID_CLIENT",
    "message": "Client authentication failed",
    "details": {
      "oauth_error": "invalid_client",
      "oauth_error_description": "Client authentication failed"
    },
    "request_id": "req_42a91c"
  }
}
```

### 4.2 Field Rules

| Field                             | Required    | Notes                            |
| --------------------------------- | ----------- | -------------------------------- |
| `error.code`                      | Yes         | Canonical Campus error code      |
| `error.message`                   | Yes         | Safe for UI, intentionally vague |
| `details.oauth_error`             | Yes         | MUST match RFC spelling exactly  |
| `details.oauth_error_description` | Optional    | MAY mirror `message`             |
| `request_id`                      | Recommended | Required for production          |

---

## 5. OAuth Authorization Endpoint (Redirect-Based Errors)

For `/authorize` endpoints using browser redirects:

* Errors MUST be returned **via redirect query parameters**
* JSON error envelopes MUST NOT be returned

### 5.1 Redirect Error Parameters

| Parameter           | Required    | Description                |
| ------------------- | ----------- | -------------------------- |
| `error`             | Yes         | OAuth error string         |
| `error_description` | Optional    | Human-readable description |
| `state`             | If provided | Echoed unchanged           |

### 5.2 Example Redirect

```
https://client.app/callback
  ?error=access_denied
  &error_description=User+denied+consent
  &state=xyz
```

### 5.3 Server-Side Requirements

Even for redirects:

* Canonical `error.code` MUST be logged
* `request_id` MUST be generated and logged
* No internal details may be reflected in redirect parameters

---

## 6. Standard OAuth Error Mapping

### 6.1 Mapping Table (Normative)

| OAuth Error             | HTTP Status | Campus Error Code            |
| ----------------------- | ----------- | ---------------------------- |
| invalid_request         | 400         | AUTH_INVALID_REQUEST         |
| invalid_client          | 401         | AUTH_INVALID_CLIENT          |
| invalid_grant           | 400         | AUTH_INVALID_GRANT           |
| unauthorized_client     | 403         | AUTH_UNAUTHORIZED_CLIENT     |
| unsupported_grant_type  | 400         | AUTH_UNSUPPORTED_GRANT       |
| invalid_scope           | 400         | AUTH_INVALID_SCOPE           |
| access_denied           | 403         | AUTH_ACCESS_DENIED           |
| server_error            | 500         | AUTH_SERVER_ERROR            |
| temporarily_unavailable | 503         | AUTH_TEMPORARILY_UNAVAILABLE |

### 6.2 Mapping Rules

* OAuth error strings MUST NOT be altered
* Campus error codes MUST be used consistently across endpoints
* Multiple internal causes MAY map to the same OAuth error

---

## 7. Token Usage Errors (campus.api Integration)

When `campus.api` validates OAuth tokens issued by `campus.auth`:

### 7.1 Invalid or Expired Token

* HTTP Status: **401 Unauthorized**
* OAuth error: `invalid_token`
* `WWW-Authenticate` header REQUIRED

```
WWW-Authenticate: Bearer
  error="invalid_token",
  error_description="The access token is invalid or expired"
```

JSON body:

```json
{
  "error": {
    "code": "AUTH_TOKEN_INVALID",
    "message": "Authentication failed",
    "details": {
      "oauth_error": "invalid_token"
    },
    "request_id": "req_d81b0f"
  }
}
```

---

### 7.2 Insufficient Scope

* HTTP Status: **403 Forbidden**
* OAuth error: `insufficient_scope`

```json
{
  "error": {
    "code": "AUTH_INSUFFICIENT_SCOPE",
    "message": "Insufficient permissions",
    "details": {
      "oauth_error": "insufficient_scope",
      "required_scopes": ["campus.read"]
    },
    "request_id": "req_aa921f"
  }
}
```

---

## 8. `WWW-Authenticate` Header Rules

The `WWW-Authenticate` header MUST be included when:

* HTTP status is **401**
* Authentication failed or token is invalid

Rules:

* Scheme MUST be `Bearer`
* Error values MUST match OAuth spec
* Header content MUST align with JSON body

---

## 9. Security Constraints (Mandatory)

To prevent authentication or authorization oracles:

* Error messages MUST NOT reveal:

  * Whether a user exists
  * Whether a client_id exists
  * Whether a password or secret was close to valid
* Redirect URI errors MUST NOT echo invalid URIs
* Token errors MUST NOT disclose:

  * Token contents
  * Expiry timestamps
  * Signature or issuer details

Specificity belongs in `error.code`, not `message`.

---

## 10. Consistency Guarantees

Across `campus.auth` and `campus.api`:

* Same error envelope shape
* Same casing and field names
* Same semantics per HTTP status
* Same logging and request ID behavior

OAuth does not introduce a parallel error system.

---

## 11. Compliance Checklist (Agent-Executable)

An implementation is compliant if and only if:

* [ ] Base Campus error envelope is preserved
* [ ] OAuth errors are mapped, not invented
* [ ] OAuth error strings match RFC exactly
* [ ] Redirect flows never return JSON errors
* [ ] `WWW-Authenticate` is present when required
* [ ] No authentication oracle exists via errors

---

## 12. Non-Goals

This specification explicitly excludes:

* OAuth client registration policy
* Token lifetime configuration
* Consent UI behavior
* Localization strategy
