# Plus11 account and backend implementation plan

## User-approved scope

The user approved enabling the managed server and database after being told that activation is one-way and development/published builds share one MySQL database. Add a real Account area and backend persistence to the existing Plus11 website; do not publish, enable auto-publishing, create external accounts, or add another OAuth provider. Preserve the existing PDF-derived design, four learning destinations, question catalogue, and anonymous demonstration screens.

## Implementation

Use the existing Next.js 16 App Router project and its registered TypeScript diagnostics. Keep server-only logic in `src/lib` and API route handlers under `src/app/api`; use `mysql2/promise` with the managed `DATABASE_URL`/TLS settings and `jose` for HS256 sessions. Manus OAuth remains server-side: a browser-visible, allowlisted callback origin, one-time state nonce, authorization-code exchange, user-info resolution, and the fixed `webdev_app_session` cookie. For Preview, derive the cookie's Secure/SameSite choice from the validated public callback origin—not the internal request scheme or `NODE_ENV`. Use request-Origin verification and an HMAC-derived CSRF token for cookie-authenticated mutations.

Keep the curriculum and public question prompts/options/hints in client-safe application content, but place every correct answer and explanation in a separate `server-only` key map. The server validates each guest or signed-in answer; it sends an explanation only after submission, and signed-in attempts are committed transactionally to the learner's records. Apply one committed, additive, idempotent SQL migration explicitly; never seed fake learner history or run schema setup at server startup. Scope every learner profile, practice, mastery, activity, and review query by the verified Manus `openId`. Treat the OAuth email as unnecessary and do not persist it. Guests retain clearly labelled illustrative demo data; signed-in users see only their real account history, including honest empty/zero states.

Connect Practice submissions/completion, Review outcomes, dashboard plan/streak/time data, Progress mastery/activity charts, and the editable display name to authenticated APIs. Use idempotency keys and database transactions for practice writes to avoid duplicate attempts when requests are retried. Missed answers enter that learner's spaced-review queue; review outcomes set future due times. Add a standalone Next.js container Dockerfile, runtime health handler, and complete deployment declaration, but do not publish.

## Design direction

This is an **Operate** surface: extend the incumbent Plus11 paper-and-ink learning interface rather than redesigning it. Keep Ink `#141414`, warm Paper `#FBFAF6`, Page `#FFFFFF`, Pencil `#5A5A55`, and Highlighter `#FFD84D` reserved for progress/selection/wins. Continue Patrick Hand headings, Nunito close-reading/body/control type, 12px minimum text, crisp rounded 1.5–2px outlines, modest corners, the existing owl mark, and comfortable whitespace. Account is a small, familiar header destination and a focused page with distinct guest, loading, signed-in, save-success/error, and sign-out states. Preserve keyboard operation, visible focus, 44px controls, contrast, responsive 375/768/1024/1440px layouts, reduced-motion behavior, and non-punitive wording. Do not introduce gradients, glass, a new palette, extra personal-data fields, or decorative card grids.

## Project structure

- `src/app/(hub)/account/page.tsx`: account page inside the existing responsive shell.
- `src/components/session-provider.tsx`, `account-screen.tsx`, and updated `app-shell.tsx`: browser auth state, account form, header entry.
- `src/app/api/auth/*`: OAuth start/callback, validated session lookup, and logout.
- `src/app/api/account`, `src/app/api/practice/check`, `src/app/api/learner/*`: profile, guest answer-check, dashboard, Progress, authenticated Practice, and Review API handlers.
- `src/lib/auth.ts`, `db.ts`, safe public `questions.ts`, server-only `question-keys.ts`, `learner-service.ts`, and `client-api.ts`: isolated session/security, database, public question content, answer key, persistence, and browser request contracts.
- `migrations/001_plus11_learning.sql` and `scripts/migrate.mjs`: explicit, deterministic additive schema deployment.
- `Dockerfile`, `next.config.ts`, and `src/app/health/route.ts`: standalone production image and schema-aware readiness route at `/health`.
- `public/manus-routes.json`: public page routes only, including `/account` and existing dynamic subject routes.

## Dependencies and operations

Add only `mysql2` and `jose`, preserve the existing pnpm 11 lifecycle allow-list and lockfile policy, and pin `pnpm@11.25.0`. Use the platform-provided OAuth and database values only at runtime; no credential goes into source, public variables, build artifacts, or logs. Run the migration once with `pnpm db:migrate`, then verify the schema and isolated authenticated handlers. Keep production origins explicit via `PLUS11_AUTH_ALLOWED_ORIGINS`; the current managed Preview origin and local loopback are supported without trusting arbitrary request hosts. Build and inspect the app, but leave publishing to the user.
