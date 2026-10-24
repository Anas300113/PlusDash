# Plus11 Delivery ToDo

## Existing frontend baseline (completed)

### Today dashboard
- [x] Build the Today dashboard with Plus owl/wordmark, a 12-day streak, “Hi Sam, ready for a quick one?”, an 18-of-30-minute progress ring, “Nearly there. 12 minutes to go.”, and a working “Continue practice” action.
- [x] Show Today’s plan with “1 of 3 done” and all three activities: Maths: fractions — 10 questions, done; Verbal reasoning: odd one out — 8 questions, 5 to go; Review: 6 cards due — about 4 minutes.
- [x] Include a Mon–Sun streak strip and Today/Learn/Progress/Review primary navigation; completed, active, and future states must be understandable without color alone.

### Learn and subject/topic selection
- [x] Show “What shall we learn? Pick a subject, then a topic.” with interactive subject cards: Maths 72% mastered/14 topics; English 58%/12; Verbal reasoning 44%/10; Non-verbal reasoning 31%/9.
- [x] Show “Pick up where it’s wobbly”: Non-verbal: rotations, 3 of the last 5 answers missed, with a working Try action.
- [x] Show “Timed mock paper” as locked with “Unlocks after 5 more topics”; it must not masquerade as an available action.
- [x] Subject selection opens topic choices; topic actions start or continue the related practice, and each of the 16 sample topics routes to a matching subject/topic question set.

### Focused practice flow
- [x] Build the verbal-reasoning question flow with a predictable close/exit action, 5-of-8 progress, timer 0:42, “Verbal reasoning, odd one out,” prompt “Which word is the odd one out?”, and support “Think about what the others have in common.”
- [x] Provide keyboard-operable, touch-friendly options A Violin, B Trumpet, C Cello, D Harp. Selecting an option and submitting it are distinct actions; the selected choice is visibly indicated.
- [x] Provide an actionable Hint, a Check answer action, and Continue after feedback. The correct answer is B — Trumpet. After checking, show a constructive accessible explanation, update session progress, and allow the next question.
- [x] Hints offer a useful clue without immediately giving away the answer. Answer feedback and focus handling must work for keyboard and assistive technology users.

### Progress and Review
- [x] Progress shows accessible overall and per-subject mastery/activity summaries based on the sample figures, plus an actionable next-step recommendation.
- [x] Review shows 6 due cards and an approximately four-minute estimate, an interactive review-start flow with progress handling, and sensible loading and empty states.

### Navigation and client-side state
- [x] Use coherent App Router navigation for Today, Learn, Progress, Review, subject/topic choices, and practice. Routes must support deep linking and browser-back-friendly behavior.
- [x] Navigation, subject/topic selection, practice, hint, answer check/feedback, continue, review start, and relevant list actions work using client-side sample data/state only for the original frontend baseline.
- [x] Provide meaningful selected, disabled, loading, empty, error, and completion states wherever applicable. Do not ship dead-looking or dead-end controls.

### Visual design system
- [x] Follow the PDF-authoritative paper-and-ink identity: Ink `#141414`, Paper `#FBFAF6`, Highlighter `#FFD84D` only for progress/wins/current emphasis, Page `#FFFFFF`, Pencil `#5A5A55`; contrast-check all combinations.
- [x] Use Patrick Hand headings and Nunito questions, answers, and close-reading text; never render text below 12px.
- [x] Use simple 2px rounded-stroke SVG icons and a Plus owl-on-open-book mark; no emoji icons.
- [x] Preserve generous whitespace, crisp outlines, restrained modest corners, and white cards. No gradients, glassmorphism, dark mode, extra color palette, or childish decoration.
- [x] Keep reusable components and design tokens consistent across all screens.

### Responsive, motion, and accessibility
- [x] Optimize mobile-first layouts around 375, 768, 1024, and 1440px; no horizontal overflow, clipped text, or obscured actions.
- [x] Use Framer Motion for subtle, meaningful 150–300ms transitions; support reduced motion and keep interactions interruptible.
- [x] Use semantic markup, visible keyboard focus, logical tab order, labels, accessible navigation state, and accessible answer/progress announcements.
- [x] Maintain body text contrast of at least 4.5:1; no state conveyed by color alone; no hover-only behavior; touch targets at least 44×44px.
- [x] Keep layout stable during loading and use respectful, non-punitive learner-facing copy.

### Engineering and handoff
- [x] Use the latest stable Next.js App Router, React, and TypeScript; use Framer Motion for the original frontend-only deliverable.
- [x] Use a maintainable component/data structure, avoid unnecessary dependencies and layout shifts, and provide app metadata/title.
- [x] Run available lint, TypeScript, and production build checks and correct applicable failures for the original frontend.
- [x] Inspect the rendered interface at mobile and desktop sizes and fix visible clipping, awkward wrapping, inconsistent spacing, and unclear states before the original frontend handoff.

## Follow-up: account area and identity
- [x] Add an accessible Account entry from the app header without displacing the existing four Today/Learn/Progress/Review destinations; add a responsive `/account` screen in the established Plus11 PDF style.
- [x] Provide clear logged-out, signing-in/loading, signed-in, sign-out, and authentication-error states. Use Manus OAuth by default because the user did not specify another identity provider; do not build or store email/password credentials.
- [x] For signed-in learners, show their actual account name; allow a learner display-name edit and sign-out. Do not collect date of birth, school, parent contact, or other unnecessary personal fields. Show provider email only if available and do not store it in the database by default.
- [x] Keep a clearly labelled guest/demo path if the learner is signed out; demo metrics may remain illustrative only and must never be shown as a signed-in learner’s real progress.

## Follow-up: authentication and privacy
- [x] After explicit owner approval, use the platform-provided Manus OAuth values and a server-side authorization-code exchange plus user-info lookup; do not expose OAuth secrets, JWT signing values, database credentials, or access tokens to client bundles.
- [x] Bind OAuth state to the initiating browser with a single-use nonce; verify it on callback; accept only a fixed in-app return path; fail closed on nonce, exchange, identity, or validation errors.
- [x] Use the exact `webdev_app_session` cookie, sign/validate HS256 sessions using `MANUS_JWT_SECRET`, validate expiry and `appId === MANUS_PROJECT_ID`, resolve the user by `openId`, and clear the same cookie on logout. Honor Preview's injected session when it is valid; never invent a logged-in demo identity or bypass auth based on `NODE_ENV`.
- [x] Set public HTTPS/Preview session cookies to `SameSite=None; Secure; HttpOnly`; handle plain local HTTP separately without basing cookie policy on internal `req.secure` or `NODE_ENV`. Keep the public OAuth redirect/callback origin correct through the Preview proxy and restrict it to the application, never an arbitrary request redirect.
- [x] Protect cookie-authenticated state-changing endpoints against cross-site requests, validate all input server-side, use parameterized SQL, and scope every read/write by the verified session's `openId` rather than a client-supplied user identifier.

## Follow-up: backend services, schema, and persistence
- [x] Before any configuration write, obtain explicit confirmation to enable the managed `server` and `database` capabilities, explain that enablement is one-way, and explain that development and published code share one MySQL database. Do not attempt to disable either capability afterward.
- [x] After approval, enable managed server+database; read `DATABASE_URL` only on the server, connect with a compatible MySQL driver and required TLS settings, and keep all credentials out of files, logs, browser code, and screenshots.
- [x] Add committed, deterministic, repeatable, additive migrations for learner profiles, practice sessions/answers, topic mastery, daily activity/plan completion, and due review items. Key all learner rows to the authenticated `openId`; do not run destructive schema changes or seed fake per-user metrics.
- [x] Make signed-in dashboard, Progress, and Review data derive from that learner's stored activity: persist real attempts/results, session completion and duration, topic mastery, plan completion, review-queue creation from missed questions, and review outcomes/due dates. New signed-in accounts start with honest empty/zero history rather than the demo's sample progress.
- [x] Keep the subject/topic catalogue and question wording as server/application content; store durable learner actions and identifiers rather than trusting client totals or storing unnecessary answer/profile data.
- [x] Keep all correct answers and explanations in a server-only answer-key module. The browser receives public prompts, options, and hints only; answer explanations are returned only after the server checks a submitted option.
- [x] Provide authenticated account/progress/practice/review API handlers and graceful loading/empty/offline/server-error paths; retain the demo-only client experience only for signed-out use. Never surface another learner's records.
- [x] Initialize and verify the additive schema explicitly; do not silently run a fresh seed or destructive migration on every app start. Health/readiness handling returns an unauthenticated success only when the runtime is ready and reveals no credentials.

## Follow-up: deployability and end-to-end readiness
- [x] Keep the App Router page manifest synchronized with the added Account page; exclude API/health endpoints.
- [x] Prepare a production container contract with the committed Dockerfile, pinned package manager/lockfile, runtime environment reads, server listening on the supplied `PORT`, and the configured health path. Do not publish the app unless the user asks.
- [x] Restart development services after managed environment changes; verify schema and health readiness, the route manifest, anonymous API rejection, HTTPS Preview OAuth redirect/cookie flags, authenticated dashboard/Progress/Review reads, hydrated guest Hint/answer/feedback interactions, mobile and desktop layouts, lint, types, migration and production build. No synthetic database writes were made.
- [ ] Complete a first real Manus OAuth sign-in and verify a profile edit plus persisted Practice/Review write across reloads in the user's own account. This final identity-backed check was not performed in order to avoid signing into the user's account or writing personal test data to the shared development/production database without the user present.
- [x] Save the completed source and migrations to managed `main`; verify the resulting checkpoint. Auto-publish is off; do not publish the app unless the user asks.
