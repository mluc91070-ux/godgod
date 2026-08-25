"""Validate docker-compose.yml without a Docker daemon.

`docker compose config` is the real check; this is what CI (and a machine with
no Docker installed) can run instead. It parses the file and asserts the
service/volume wiring, so a typo is caught before the first deploy.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - dev dependency
    print("pyyaml is not installed; run pip install -r backend/requirements-dev.txt")
    raise SystemExit(2) from None

COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"

EXPECTED_SERVICES = {"db", "backend", "frontend"}


def main() -> int:
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    failures: list[str] = []

    services = data.get("services", {})
    missing = EXPECTED_SERVICES - set(services)
    if missing:
        failures.append(f"missing services: {sorted(missing)}")

    db = services.get("db", {})
    if "pgvector" not in str(db.get("image", "")):
        failures.append("db must use a pgvector-capable image")
    if "healthcheck" not in db:
        failures.append("db needs a healthcheck so backend can wait for it")

    backend = services.get("backend", {})
    if backend.get("depends_on", {}).get("db", {}).get("condition") != "service_healthy":
        failures.append("backend must wait for db to be healthy")
    if "alembic upgrade head" not in str(backend.get("command", "")):
        failures.append("backend must run migrations on start")
    database_url = str(backend.get("environment", {}).get("DATABASE_URL", ""))
    if not database_url.startswith("postgresql+psycopg://"):
        failures.append("backend DATABASE_URL must target postgresql+psycopg")

    for name, service in services.items():
        for key in ("environment",):
            for env_key, env_value in (service.get(key) or {}).items():
                if "KEY" in env_key.upper() or "TOKEN" in env_key.upper():
                    if env_value:
                        failures.append(f"{name}.{env_key} must not carry a literal secret")

    declared_volumes = set(data.get("volumes") or {})
    for name, service in services.items():
        for mount in service.get("volumes", []):
            source = str(mount).split(":", 1)[0]
            if not source.startswith(".") and source not in declared_volumes:
                failures.append(f"{name} mounts undeclared volume {source}")

    for failure in failures:
        print(f"[FAIL] {failure}")
    if not failures:
        print(f"[ok  ] docker-compose.yml parses; services {sorted(services)}")
        print("       note: not executed — no Docker daemon on this machine")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
