"""Run offline checks, lint and dependency validation, keeping logs in project."""

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime
from importlib import metadata
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="docs/VALIDATION_RESULTS.json")
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(ROOT):
        parser.error("Output must stay inside this project")
    cache = ROOT / ".cache/tmp"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.update(TEMP=str(cache), TMP=str(cache), PYTHONUTF8="1")
    commands = [
        [sys.executable, "-m", "pytest", "-q"],
        [sys.executable, "-m", "ruff", "check", "."],
        [sys.executable, "-m", "ruff", "format", "--check", "."],
        [sys.executable, "-m", "pip", "check"],
    ]
    checks = []
    for command in commands:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300 if "pytest" in command else 120,
        )
        command_output = result.stdout + result.stderr
        checks.append(
            {"command": command[1:], "exit_code": result.returncode, "output": command_output}
        )
        print(command_output, end="", flush=True)
    dependencies = {}
    for name in (
        "httpx",
        "protobuf",
        "gtfs-realtime-bindings",
        "tzdata",
        "pytest",
        "ruff",
        "customtkinter",
        "darkdetect",
    ):
        dist = metadata.distribution(name)
        dependencies[name] = {
            "version": dist.version,
            "requires_python": dist.metadata.get("Requires-Python"),
            "installed_wheel": dist.read_text("WHEEL"),
        }
    report = {
        "checked_at": datetime.now(ZoneInfo("America/Bogota")).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "checks": checks,
        "dependencies": dependencies,
        "all_passed": all(check["exit_code"] == 0 for check in checks),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
