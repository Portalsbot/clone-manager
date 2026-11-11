"""Resolve runtime data files independently of the installed Python package location."""
from __future__ import annotations

import os
from pathlib import Path


def _contains_required_data(root: Path) -> bool:
    return (
        (root / "config" / "command_responses.json").is_file()
        and (root / "assets" / "branding.jpg").is_file()
    )


def resolve_app_data_dir() -> Path:
    """Find the Docker/project data directory.

    In Render's Docker image the project data is copied to /app, while the
    Python package itself is installed under site-packages. Prefer the
    explicit setting, then the process working directory, then the source
    checkout layout used by local development.
    """
    candidates: list[Path] = []
    configured = os.getenv("CLONE_MANAGER_DATA_DIR", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser().resolve())

    candidates.append(Path.cwd().resolve())
    candidates.append(Path(__file__).resolve().parents[2])

    searched: list[str] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        searched.append(str(candidate))
        if _contains_required_data(candidate):
            return candidate

    locations = ", ".join(searched) or "(none)"
    raise RuntimeError(
        "Could not locate Clone Manager runtime data "
        "(config/command_responses.json and assets/branding.jpg). "
        f"Set CLONE_MANAGER_DATA_DIR to the directory containing config/ and assets/. "
        f"Searched: {locations}"
    )


APP_DATA_DIR = resolve_app_data_dir()
