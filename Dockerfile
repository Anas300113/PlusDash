# Use Docker Official Images from ECR Public to avoid Docker Hub anonymous-pull limits.
# Keep Node and Python on the same Debian suite for compatible system libraries.
FROM public.ecr.aws/docker/library/node:22.23.3-trixie-slim AS node-base
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@11.25.0 --activate
ENV NEXT_TELEMETRY_DISABLED=1

FROM node-base AS node-deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM node-base AS builder
COPY --from=node-deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build

FROM public.ecr.aws/docker/library/python:3.12.15-slim-trixie AS python-deps
WORKDIR /build
COPY requirements-runtime.lock ./requirements-runtime.lock
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements-runtime.lock

FROM public.ecr.aws/docker/library/python:3.12.15-slim-trixie AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    PLUS_API_PORT=8001 \
    PLUS_RUN_MIGRATIONS=1 \
    PATH="/opt/venv/bin:/usr/local/bin:/usr/bin:/bin"
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1001 nodejs \
    && useradd --system --uid 1001 --gid nodejs nextjs
COPY --from=node-base /usr/local/ /usr/local/
COPY --from=python-deps /opt/venv /opt/venv
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/src ./src
COPY --from=builder --chown=nextjs:nodejs /app/scripts/supervise.py ./scripts/supervise.py
USER nextjs
EXPOSE 3000
CMD ["python3", "scripts/supervise.py", "--production"]
