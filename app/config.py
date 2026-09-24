"""config.yaml / .env / presets 로딩."""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
USER_ENV = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".config") / "AIShorts" / "settings.env"
load_dotenv(ROOT / ".env")
load_dotenv(USER_ENV, override=True)


def _read_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class _PresetDumper(yaml.SafeDumper):
    """여러 줄 문자열을 읽기 좋은 블록(|) 형태로 저장한다."""


def _str_representer(dumper: yaml.Dumper, data: str):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_PresetDumper.add_representer(str, _str_representer)


def load_config() -> dict[str, Any]:
    cfg = _read_yaml(ROOT / "config.yaml")
    paths = cfg.setdefault("paths", {})
    for key, default in (("output", "output"), ("presets", "presets"), ("assets", "assets"), ("styles", "styles")):
        paths[key] = str(ROOT / paths.get(key, default))
    return cfg


def load_presets(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    presets: dict[str, dict[str, Any]] = {}
    for p in sorted(Path(cfg["paths"]["presets"]).glob("*.yaml")):
        data = _read_yaml(p)
        presets[data.get("id", p.stem)] = data
    return presets


# 웹 UI 에서 편집할 수 있는 프리셋 항목
EDITABLE_PRESET_FIELDS = ("name", "description", "tone", "script_rules", "image_style",
                          "research_queries_suffix", "image_provider", "visual_mode")


def save_preset(cfg: dict[str, Any], preset_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """프리셋 yaml 의 편집 가능한 항목만 덮어쓰고, 저장된 내용을 돌려준다."""
    path = Path(cfg["paths"]["presets"]) / f"{preset_id}.yaml"
    if not path.exists():
        # id 와 파일명이 다를 수 있으므로 내용으로 찾는다
        for p in Path(cfg["paths"]["presets"]).glob("*.yaml"):
            if _read_yaml(p).get("id") == preset_id:
                path = p
                break
        else:
            raise FileNotFoundError(f"프리셋을 찾을 수 없습니다: {preset_id}")

    data = _read_yaml(path)
    for k in EDITABLE_PRESET_FIELDS:
        if k in updates:
            data[k] = updates[k]
    if "subtitle" in updates and isinstance(updates["subtitle"], dict):
        data.setdefault("subtitle", {}).update(updates["subtitle"])
    if "voice" in updates and isinstance(updates["voice"], dict):
        data.setdefault("voice", {}).update(updates["voice"])

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, Dumper=_PresetDumper, allow_unicode=True, sort_keys=False,
                  default_flow_style=False, width=1000)
    return data


def merge_options(cfg: dict[str, Any], preset: dict[str, Any], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """config 기본값 위에 프리셋과 사용자 옵션을 얹어 실행용 설정을 만든다."""
    out = copy.deepcopy(cfg)
    overrides = overrides or {}

    if overrides.get("llm_provider"):
        out["llm"]["provider"] = overrides["llm_provider"]
    if overrides.get("llm_model"):
        out["llm"]["model"] = overrides["llm_model"]
    elif overrides.get("llm_provider") == "openai":
        out["llm"]["model"] = out["llm"].get("openai_model", "gpt-5-mini")
    if overrides.get("tts_provider"):
        out["tts"]["provider"] = overrides["tts_provider"]
    # 이미지 provider 우선순위: config 기본값 < 프리셋 < UI 선택
    if preset.get("image_provider"):
        out["images"]["provider"] = preset["image_provider"]
    if overrides.get("image_provider"):
        out["images"]["provider"] = overrides["image_provider"]
    if overrides.get("image_size"):
        out["images"]["image_size"] = overrides["image_size"]
    if overrides.get("target_seconds"):
        out["video"]["target_seconds"] = int(overrides["target_seconds"])

    # 자막은 선택 사항: 프리셋 subtitle.enabled 기본값 < UI 체크박스
    sub = preset.get("subtitle") or {}
    out["video"]["subtitles"] = bool(overrides.get("subtitles", sub.get("enabled", True)))
    out["video"]["titles"] = bool(overrides.get("titles", sub.get("titles", True)))

    provider = out["tts"]["provider"]
    voice = overrides.get("voice") or (preset.get("voice") or {}).get(provider) or out["tts"]["voices"].get(provider, "")
    out["tts"]["voice"] = voice
    out["preset"] = preset
    return out


def env(name: str) -> str | None:
    v = os.getenv(name, "").strip()
    return v or None
