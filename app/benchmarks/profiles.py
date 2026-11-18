"""Safe local JSON loading; adding a profile requires no changes to the schema."""
from __future__ import annotations

import re
from pathlib import Path

from .models import BenchmarkProfile

PROFILE_DIR = Path(__file__).resolve().parent / "profiles"
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,79}$")


def profile_names(directory: Path | None = None) -> list[str]:
    return sorted(p.stem for p in (directory or PROFILE_DIR).glob("*.json") if NAME_RE.fullmatch(p.stem))


def load_profile(name: str, directory: Path | None = None) -> BenchmarkProfile:
    if not NAME_RE.fullmatch(name):
        raise ValueError("benchmark profile name must contain only lowercase letters, digits and underscores")
    path = (directory or PROFILE_DIR) / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"benchmark profile not found: {name}; available: {', '.join(profile_names(directory))}")
    profile = BenchmarkProfile.model_validate_json(path.read_text(encoding="utf-8-sig"))
    if profile.profile_name != name:
        raise ValueError("profile_name does not match its filename")
    return profile
