"""Runtime/build version is read from project metadata; never duplicated in code."""

import tomllib
from importlib.metadata import version
from pathlib import Path


def app_version():
    metadata = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if metadata.exists():
        return tomllib.loads(metadata.read_text(encoding="utf-8"))["project"]["version"]
    return version("transmitracker")
