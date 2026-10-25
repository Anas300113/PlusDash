# Plus11 FastAPI integration

This repository combines the Plus11 Next.js 16 App Router frontend with the selected Python/FastAPI learning backend. Next.js is the only public listener. FastAPI binds to loopback (`127.0.0.1:8001`) and is called only by server-side BFF routes; browser requests remain same-origin.

## Local development

1. Install the pinned frontend dependencies with `pnpm install --frozen-lockfile`.
2. Create the Python environment with `pnpm setup:python`.
3. Copy `.env.example` to an ignored local `.env` and configure OAuth. Use an isolated SQLite URL such as `DATABASE_URL=sqlite:///./elevenplus.db` for local development; never point write-oriented tests at the managed MySQL database.
4. Start both services with `pnpm dev`. The supervisor starts FastAPI privately, then Next on `PORT` (3000 by default). For a new local SQLite database, the explicit additive migration runs after both listeners bind. For a local MySQL configuration, run `pnpm api:migrate` only after reviewing the target.

FastAPI `GET /api/health` is a liveness probe. Next `GET /health` checks FastAPI's read-only `GET /api/ready`; readiness is successful only when the required database schema is available.

## Tests and checks

Run `pnpm lint`, `pnpm typecheck`, and `pnpm build`. Run the Python suite with `pnpm api:test` and syntax validation with `pnpm api:compile`. The Python write-path tests use isolated SQLite fixtures. Do not run migrations or write-oriented tests against the managed development/production-shared MySQL database.

## Identity and guest mode

The guest/demo learning experience uses frontend-only sample state. It is never written to the backend or represented as an authenticated learner record. Signed-in Next.js routes validate the Manus session cookie, enforce same-origin/CSRF checks on mutations, and forward the signed session only in a server-side Bearer header. FastAPI verifies HS256, expiry, and `appId === MANUS_PROJECT_ID`, derives an opaque stable learner ID from the verified provider `openId`, ignores client-supplied identity, and scopes profile, practice, progress, and review data to that ID.

FastAPI rejects unauthenticated requests to `/api/me/*`. Legacy ID-only student routes remain fail-closed in real-data mode. Signed-in practice uses only the approved-question catalog. Answer keys and explanations are returned only after an answer check or an explicit review-card reveal. If there are no approved questions or saved learner records, the app shows an honest empty state instead of guest sample metrics.

## Managed database and production

`DATABASE_URL` is consumed at runtime only. `mysql://` is normalized to SQLAlchemy's PyMySQL dialect, and MySQL connections require certificate and hostname verification. `PLUS_MYSQL_SSL_CA` can supply an approved CA bundle if required. Never put database, OAuth, or JWT secrets in `NEXT_PUBLIC_*` variables, browser code, or committed files.

The optional `python -m src.core.migrate --reconcile-page-provenance` operation rewrites known invalid source-page pointers in existing content rows. It is intentionally not part of schema migration or production startup; invoke it only after reviewing and explicitly approving that data correction.

The managed development and production environments share one database. The migration command is additive and idempotent; it creates missing schema only and does not seed generated questions or delete learner rows. The production Docker entrypoint sets `PLUS_RUN_MIGRATIONS=1`; the supervisor first binds FastAPI and Next, then runs the explicit migration command while readiness remains false until the read-only database/schema probe passes. To disable startup migrations for a deployment whose schema is already prepared, set `PLUS_RUN_MIGRATIONS=0`; readiness will still fail if required schema is missing.
