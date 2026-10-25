#!/usr/bin/env python3
"""Run private FastAPI and the public Next.js app as one container/service."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def python_with_fastapi() -> str:
    candidates = [
        ROOT / ".venv" / "bin" / "python",
        Path("/opt/venv/bin/python"),
        Path(sys.executable),
    ]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        check = subprocess.run(
            [str(candidate), "-c", "import fastapi, sqlalchemy, jwt"],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False,
        )
        if check.returncode == 0:
            return str(candidate)
    raise SystemExit(
        "FastAPI dependencies are missing. Run `pnpm setup:python` before `pnpm dev`."
    )


def wait_for_http(process: subprocess.Popen, url: str, *, allow_redirect: bool = True) -> None:
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError(f"Service exited before becoming ready at {url}.")
        try:
            with urlopen(url, timeout=0.5) as response:
                if 200 <= response.status < 300 or (allow_redirect and 300 <= response.status < 400):
                    return
        except (URLError, TimeoutError, OSError):
            time.sleep(0.2)
    raise RuntimeError(f"Service did not become ready at {url}.")


def terminate(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def _stop_on_termination(_signum, _frame) -> None:
    raise KeyboardInterrupt


def main() -> int:
    production = "--production" in sys.argv[1:]
    api_port = int(os.environ.get("PLUS_API_PORT", "8001"))
    public_port = int(os.environ.get("PORT", "3000"))
    if not (1024 <= api_port <= 65535 and 1024 <= public_port <= 65535):
        raise SystemExit("PORT and PLUS_API_PORT must be in 1024..65535.")
    if api_port == public_port:
        raise SystemExit("PORT and PLUS_API_PORT must be different.")
    if production and not (os.environ.get("DATABASE_URL") or os.environ.get("PLUS_DATABASE_URL")):
        raise SystemExit("DATABASE_URL is required in production.")

    env = os.environ.copy()
    if not production and not (env.get("DATABASE_URL") or env.get("PLUS_DATABASE_URL")):
        # A fresh local SQLite DB is isolated from the managed MySQL database.
        env["DATABASE_URL"] = "sqlite:///./elevenplus.db"
    env["PLUS_API_BASE_URL"] = f"http://127.0.0.1:{api_port}"
    env["PLUS_API_PORT"] = str(api_port)
    env["PORT"] = str(public_port)
    env["HOSTNAME"] = "0.0.0.0"
    env.setdefault("PLUS_REAL_STUDENT_DATA", "1")
    env.setdefault("PLUS_REQUIRE_STUDENT_IDENTITY", "1")

    python = python_with_fastapi()
    database_url = env.get("DATABASE_URL") or env.get("PLUS_DATABASE_URL", "")
    run_migrations = (
        production and env.get("PLUS_RUN_MIGRATIONS", "1") == "1"
    ) or (
        not production and database_url.startswith("sqlite:")
        and env.get("PLUS_RUN_MIGRATIONS", "1") == "1"
    )

    api = subprocess.Popen(
        [python, "-m", "uvicorn", "src.api.main:app", "--host", "127.0.0.1",
         "--port", str(api_port), "--no-access-log"],
        cwd=ROOT, env=env,
    )
    web = None
    migration = None
    signal.signal(signal.SIGTERM, _stop_on_termination)
    signal.signal(signal.SIGINT, _stop_on_termination)
    try:
        # Bind both listeners first; readiness remains false while preparation runs.
        wait_for_http(api, f"http://127.0.0.1:{api_port}/api/health")
        if production:
            command = ["node", "server.js"]
        else:
            next_bin = ROOT / "node_modules" / ".bin" / "next"
            if not next_bin.exists():
                raise RuntimeError("Next.js dependencies are missing; run `pnpm install` first.")
            command = [str(next_bin), "dev", "--hostname", "0.0.0.0", "--port", str(public_port)]
        web = subprocess.Popen(command, cwd=ROOT, env=env)
        wait_for_http(web, f"http://127.0.0.1:{public_port}/")

        if run_migrations:
            migration = subprocess.Popen(
                [python, "-m", "src.core.migrate"], cwd=ROOT, env=env,
            )
            while migration.poll() is None:
                if api.poll() is not None or web.poll() is not None:
                    terminate(migration)
                    raise RuntimeError("A service exited while the additive migration was running.")
                time.sleep(0.2)
            if migration.returncode != 0:
                raise RuntimeError("The explicit Plus11 additive database migration failed.")

        if production:
            wait_for_http(api, f"http://127.0.0.1:{api_port}/api/ready")
            wait_for_http(web, f"http://127.0.0.1:{public_port}/health")
        while web.poll() is None:
            if api.poll() is not None:
                raise RuntimeError("FastAPI exited while Next.js was running.")
            time.sleep(0.25)
        return web.returncode or 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"Plus11 runtime error: {exc}", file=sys.stderr)
        return 1
    finally:
        terminate(migration)
        terminate(web)
        terminate(api)


if __name__ == "__main__":
    raise SystemExit(main())
