"""Source provenance is separate from production profiles and output media rights."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field

from . import benchmark
from .benchmark_models import Contract, Identifier, Text


class Finding(Contract):
    name: Text
    analysis_depth: Literal["direct_observation", "metadata_and_transcript", "catalog_only", "partial_observation"]
    structure: list[Text] = Field(min_length=1)
    derived_profiles: list[Identifier] = Field(default_factory=list)
    next_work: Text | None = None


class BenchmarkSource(Contract):
    schema_version: Literal[1] = 1
    id: Identifier
    name: Text
    analyzed_at: date
    genre: Text
    references: list[Text] = Field(min_length=1)
    analysis_records: list[Text] = Field(min_length=1)
    observed_structure: list[Text] = Field(min_length=1)
    observed_patterns: list[Text] = Field(min_length=1)
    adopted_elements: list[Text] = Field(min_length=1)
    do_not_copy: list[Text] = Field(min_length=1)
    derived_profiles: list[Identifier] = Field(min_length=1)
    findings: list[Finding] = Field(default_factory=list)
    # Optional provenance for a future Radar; no collection/translation implemented.
    source_country: str | None = None
    source_language: str | None = None
    target_market: str | None = None
    trend_date: date | None = None
    trend_signal: str | None = None
    localization_notes: str | None = None


def load_source(name: str, root: Path | None = None):
    from pydantic import TypeAdapter
    TypeAdapter(Identifier).validate_python(name)
    base = root or benchmark.PROFILE_ROOT
    source = BenchmarkSource.model_validate_json((base / "sources" / f"{name}.json").read_text(encoding="utf-8"))
    if source.id != name:
        raise ValueError("source ID must match filename")
    if len(set(source.derived_profiles)) != len(source.derived_profiles):
        raise ValueError("duplicate source/profile links")
    return source


def inventory(root: Path | None = None):
    base = root or benchmark.PROFILE_ROOT
    profiles = {p["id"]: p for p in benchmark.profiles(base)}
    sources = {p.stem: load_source(p.stem, base) for p in sorted((base / "sources").glob("*.json"))}
    for sid, src in sources.items():
        for name in src.derived_profiles:
            if name not in profiles or sid not in profiles[name]["source_ids"]:
                raise ValueError(f"broken source/profile relationship: {sid} -> {name}")
        for finding in src.findings:
            if any(name not in src.derived_profiles for name in finding.derived_profiles):
                raise ValueError(f"finding links outside source profiles: {sid}")
    for name, profile in profiles.items():
        for sid in profile["source_ids"]:
            if sid not in sources or name not in sources[sid].derived_profiles:
                raise ValueError(f"broken profile/source relationship: {name} -> {sid}")
    return dict(source_count=len(sources), profile_count=len(profiles),
                sources=[json.loads(src.model_dump_json()) for src in sources.values()],
                profiles=list(profiles.values()))
