---
id: ARCH-SEC-001
kind: security_spec
status: accepted
related: [NFR-002, NFR-003]
---

# Security and privacy

## Threat priorities

1. Cross-workspace data access.
2. Unsafe file uploads.
3. Prompt injection through uploaded or retrieved content.
4. Secret leakage.
5. Excessive provider data sharing.
6. Abuse and unbounded cost.
7. Insecure exports or public object URLs.

## Controls

### Authentication and sessions

- Use secure, HttpOnly, SameSite cookies.
- Rotate session identifiers after authentication.
- Replace prior sessions for the account after login; a token that predates a
  successful login must not remain usable.
- Add CSRF protection where applicable.
- Rate-limit login and recovery.
- Store passwords with a modern password hash through an established auth library.

### Authorization

- Enforce workspace ownership in repository queries.
- Never trust workspace or user IDs from the browser without session validation.
- Derive the current user from an HttpOnly server session; a workspace selector may only choose a verified membership.
- Add negative tests for every read/write endpoint.

### Files

- Allow only explicit media types.
- Decode and verify the actual image format; never trust the multipart MIME type.
- Limit file size, dimensions, and decompression ratio.
- Never use user-supplied filenames as storage paths.
- Keep object keys opaque and authorize every read through a private endpoint
  (or an equivalently short-lived signed URL).
- Strip unnecessary metadata where policy requires it.

### LLM boundary

- Treat user text and image-extracted text as untrusted data.
- Model tools are allowlisted and parameter-validated.
- No arbitrary URL fetch tool in MVP.
- No direct database tool.
- System instructions and business rules are assembled server-side.
- Store prompt versions and safe metadata for audit.

### Privacy

- Explicitly disclose which content may be sent to an external AI provider.
- Provide demo/local-provider mode.
- Do not train on customer data without separate explicit consent.
- Support deletion and export requests.

### Cost protection

- Per-user and per-workspace generation limits.
- Maximum prompt/context size.
- Provider timeout.
- Retry limit with exponential backoff.
- Circuit breaker for failing providers.

### HTTP baseline

- Every response carries an opaque request ID for support and safe correlation.
- Server responses send anti-sniffing, anti-framing, referrer and permissions-policy headers.
- Requests exceeding the configured body limit are rejected before route handling.
- Login, registration and generation have a configurable rate limit. Development
  uses a local deterministic adapter; production uses Redis and refuses to
  start when the shared limiter is unavailable.
- Production startup rejects demo providers, local object storage, an absent
  Redis URL, the documented development secret, and non-HTTPS allowed origins.

## Security acceptance tests

- User A cannot retrieve User B’s project by ID.
- SVG and executable uploads are rejected in MVP.
- A malformed image with a valid-looking header is rejected.
- Oversized images are rejected before provider call.
- Prompt content cannot invoke an unauthorized tool.
- Provider key never appears in browser bundle or API response.
- Logs redact authorization headers and secrets.
