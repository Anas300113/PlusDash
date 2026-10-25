# ADR-002: Student identity and data ownership

- **Status:** Accepted; the signed Manus identity bridge is implemented for Plus11 `/api/me/*` (2026-10-25).
- **Supersedes:** The original Phase 1-only identity gap note dated 2026-10-15. Legacy ID-only routes remain unavailable in real-data mode.

## Context

The existing FastAPI learning engine has historical student routes that accept a bare `student_id` in a path or payload. Such an identifier is not authentication: a caller could claim another learner's ID. Plus11 now has an established Manus OAuth session in Next.js, and the user selected FastAPI as the authoritative account-backed learning service.

## Decision

1. Next.js remains the browser-facing BFF. It validates the `webdev_app_session` cookie and forwards the original signed session only in a server-to-server Bearer header to FastAPI over the private loopback connection. Browser requests do not call FastAPI directly.
2. FastAPI validates only HS256 tokens, verifies the signature and expiry, and requires `appId === MANUS_PROJECT_ID`. It derives an opaque deterministic learner ID from the verified provider `openId` using a keyed HMAC and the server-only `MANUS_JWT_SECRET`. Client-supplied IDs, headers, query parameters, and path values never establish ownership for `/api/me/*`.
3. Profile, approved catalog, dashboard, progress, practice-session, and review routes under `/api/me/*` use that derived learner ID for every read and write. Session and review ownership is checked in the backend. Practice responses omit answer keys until a checked answer; review answers are returned only from the explicit reveal action.
4. Legacy ID-only routes are not adapted by trusting an `X-Student-Id` header. `PLUS_REAL_STUDENT_DATA` defaults to enabled and those routes fail closed. The optional `PLUS_REQUIRE_STUDENT_IDENTITY` header comparison is not authentication and may only be used as a defensive check in explicitly isolated/demo contexts when real-data mode is disabled.
5. No parent principal, parent data-sharing relation, email/password store, or migration of historical bare-ID records is introduced. Existing records cannot be attributed to an authenticated learner without a verified mapping and must not be silently claimed as that learner's history.

## Session and operational constraints

The existing Next.js `webdev_app_session` cookie remains HttpOnly. Its attributes are `SameSite=None; Secure` for public HTTPS/embedded Preview, and local plain HTTP is handled separately. OAuth state remains bound to the initiating browser and return URLs stay restricted to an allowed application origin and fixed callback path. State-changing BFF routes retain origin and CSRF verification.

The FastAPI listener binds to `127.0.0.1:8001`; Next.js is the only public service. JWT/database secrets are read at runtime and are not placed in browser bundles or build artifacts. Internal API access logs are disabled so the Bearer token is not written in ordinary request logs.

## Database and migration constraints

The FastAPI SQLAlchemy models own authenticated learning data. The managed MySQL URL is normalized to the PyMySQL dialect and requires verified TLS certificate and hostname checks. Schema changes use the explicit additive, idempotent migration runner; import-time schema mutation is prohibited. No synthetic account progress or unapproved question bank is seeded. Tests use isolated SQLite databases; do not run write-oriented checks against the MySQL database shared by development and production.

The internal identity is deterministic while the signing secret remains stable. Rotating `MANUS_JWT_SECRET` changes the derived identifier and therefore requires a separately reviewed identity-mapping migration if existing learner data must remain accessible; do not rotate it silently.

## Verification

`tests/test_plus11_identity.py` covers valid/invalid signed claims, account separation, client-ID spoofing, approved content, answer disclosure, and practice-session ownership using isolated SQLite. `tests/test_student_identity.py` retains checks that legacy ID-only access remains fail-closed when real-data mode is on. A first real learner sign-in and personal practice/review write requires the user to be present; no personal account data is used for automated tests.

## Consequences and alternatives

The new `/api/me/*` surface provides a verified ownership boundary without replacing the upstream learning engine or exposing its legacy bare-ID contract. Signed-in metrics are derived from backend records; signed-out guest metrics remain local sample data. Parent access and retroactive ownership of old records remain explicitly out of scope.

- **Trust `X-Student-Id`:** rejected because a caller can spoof it.
- **Expose FastAPI directly to the browser:** rejected because it would widen CORS, token-handling, and identity attack surface.
- **Create a second Next.js learner store:** rejected because it duplicates authoritative learning state.
