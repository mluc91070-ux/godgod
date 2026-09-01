"""Run every phase gate, each against its own fresh database.

The gates assert exact counts — "144 measurements ingested, not 147" — so they
only mean anything on a database nobody else has touched. Running them in one
shell against the shared dev database makes an earlier gate's seed data look
like a later gate's bug, which is a false alarm and worse than no check at all.

Each gate therefore runs in its own process with its own temporary SQLite file.

    backend/.venv/Scripts/python scripts/check_all.py

`preflight.py` is deliberately not included: it checks the environment you are
about to deploy with, so it must see the real one, not a temporary database.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GATES = (
    ("PHASE 1  foundation", "check_phase1.py"),
    ("PHASE 2  memory", "check_phase2.py"),
    ("PHASE 3  observation", "check_phase3.py"),
    ("PHASE 4-6 research", "check_phase4.py"),
    ("PHASE 8  chain + market", "check_phase8.py"),
    ("PHASE 9  live stream", "check_phase9.py"),
    ("PHASE 10 public pages", "check_phase10.py"),
    ("model layer", "check_agents.py"),
)


def run(label: str, script: str, verbose: bool) -> bool:
    with tempfile.TemporaryDirectory(prefix="godgod-gate-") as workdir:
        env = {
            **os.environ,
            "DATABASE_URL": f"sqlite+aiosqlite:///{Path(workdir).as_posix()}/gate.db",
            "DEMO_MODE": "true",
            "GODGOD_AUTO_SEED": "0",
            "PYTHONIOENCODING": "utf-8",
        }
        # The command is this interpreter plus a script name from GATES above;
        # nothing here comes from outside the file.
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(ROOT / script)],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    ok = result.returncode == 0
    print(f"[{'ok  ' if ok else 'FAIL'}] {label:<24} {script}")
    if verbose or not ok:
        for line in (result.stdout + result.stderr).splitlines():
            if verbose or line.startswith("[FAIL]") or "Error" in line or "Traceback" in line:
                print(f"        {line}")
    return ok


def main() -> int:
    verbose = "--verbose" in sys.argv
    failed = [label for label, script in GATES if not run(label, script, verbose)]

    print()
    if failed:
        print(f"gates: FAIL ({len(failed)} of {len(GATES)}) — {', '.join(failed)}")
        return 1
    print(f"gates: PASS ({len(GATES)} of {len(GATES)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
