# Plus11

Plus11 is a calm, paper-and-ink learning companion for learners preparing for 11-plus-style assessments. It combines a short daily plan, Maths, English, Verbal and Non-verbal Reasoning practice, progress, and spaced review in one mobile-first app.

The interface follows the supplied `Plus11+AppDesign.pdf`: warm paper, ink outlines, restrained highlighter-yellow progress, Patrick Hand headings, Nunito reading text, and the owl-on-an-open-book mark. See [DESIGN.md](DESIGN.md) for the design tokens and interaction rules.

## Product surfaces

- **Today:** daily plan, activity progress, streak, and a clear next action.
- **Learn:** subjects, approved topics for signed-in learners, and topic practice.
- **Practice:** focused question flow with hints, checked-answer feedback, retry, and resume.
- **Progress and Review:** account-backed mastery/activity and due-card review.
- **Account:** Manus sign-in, profile, and sign-out.
- **Guest/demo:** frontend-only example content and state, separate from authenticated history.

## Architecture

The Next.js 16 App Router application is the public web app and same-origin backend-for-frontend (BFF). It runs the learner interface and proxies signed-in operations to the existing Python 3.12/FastAPI learning service. FastAPI binds only to `127.0.0.1:8001`; the Next.js server is the only public listener. SQLAlchemy owns the learning schema in the managed MySQL database, using PyMySQL with certificate and hostname-verified TLS. Local tests use isolated SQLite.

Manus OAuth establishes the signed application session. The BFF forwards that signed token to FastAPI only in a server-side Bearer header. FastAPI validates the HS256 signature, expiry, and project identity, derives a stable opaque learner ID, and scopes account-backed reads and writes to that learner. Account practice uses only approved questions; answer keys and explanations are withheld until answer checking or explicit review-card reveal.

## Run locally

Prerequisites: Node.js 22, pnpm 11.25.0, and Python 3.12.

```sh
pnpm install --frozen-lockfile
pnpm setup:python
cp .env.example .env
pnpm dev
```

The development supervisor starts FastAPI privately and then Next.js on `PORT` (3000 by default). Without a database URL, it uses a local SQLite file. Configure the Manus OAuth values in the ignored `.env` only when testing account sign-in; do not commit `.env` or put server secrets in `NEXT_PUBLIC_*` variables.

## Checks and schema

```sh
pnpm lint
pnpm typecheck
pnpm build
pnpm api:test
pnpm api:compile
```

The Python write-path suite is designed for isolated SQLite fixtures. Never point tests at the managed database, which is shared between development and production.

`pnpm db:migrate` (or `python -m src.core.migrate`) is an explicit, additive, idempotent schema operation. It creates missing tables and adds missing columns/indexes; it does not seed questions, drop rows, or rewrite existing content. The optional `python -m src.core.migrate --reconcile-page-provenance` operation changes existing content metadata and is separate from schema migration; use it only after explicit review and approval.

For local development and deployment details, read [PLUS11_INTEGRATION.md](PLUS11_INTEGRATION.md). The original backend-specific documentation is preserved at [docs/UPSTREAM_FASTAPI_README.md](docs/UPSTREAM_FASTAPI_README.md).
