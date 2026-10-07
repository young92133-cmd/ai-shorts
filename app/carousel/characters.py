"""Character Registry — 인스타툰 고정 캐릭터의 Character Bible 저장소.

characters/<id>/bible.json 하나가 캐릭터 하나다. id 는 ASCII 만 쓴다(Windows/OneDrive 한글 파일명 문제).
여러 콘텐츠에서 같은 캐릭터를 다시 쓰고, 생성 이미지는 characters/<id>/generated/ 에 캐시해
같은 감정·자세는 같은 그림이 나오게 한다.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parents[2] / "characters"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{1,39}$")
BIBLE = "bible.json"
DEFAULT_CHARACTER = "tory_01"


class CharacterBible(BaseModel):
    id: str
    name: str
    role: str = ""
    appearance: dict[str, Any] = Field(default_factory=dict,
                                       description="face / skin_tone / hair_style / hair_color / eye_color / features")
    default_outfit: dict[str, Any] = Field(default_factory=dict, description="top / top_color / bottom / bottom_color")
    accessories: list[str] = Field(default_factory=list)
    personality: str = ""
    speech_style: str = ""
    visual_style: str = ""
    reference_images: list[str] = Field(default_factory=list,
                                        description="파일명에 감정·자세가 들어가면 그 컷에 우선 사용 (예: happy_pointing.png)")
    mascot: dict[str, Any] = Field(default_factory=dict,
                                   description="AI 이미지가 없을 때 앱이 직접 그리는 마스코트의 색·머리 모양")
    prompt_lock: str = Field(default="", description="모든 생성 프롬프트 앞에 고정으로 붙는 외형 설명 (비우면 자동)")

    @field_validator("id")
    @classmethod
    def _ascii_id(cls, v: str) -> str:
        if not ID_RE.match(v):
            raise ValueError("캐릭터 id 는 영문 소문자·숫자·밑줄 2~40자여야 합니다 (예: tory_01)")
        return v


def _root(root: Path | None) -> Path:
    return Path(root) if root else ROOT


def list_characters(root: Path | None = None) -> list[CharacterBible]:
    base = _root(root)
    out = []
    for path in sorted(base.glob(f"*/{BIBLE}")):
        try:
            out.append(CharacterBible.model_validate_json(path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 - 깨진 파일 하나 때문에 목록 전체가 실패하지 않게
            continue
    return out


def get_character(char_id: str, root: Path | None = None) -> CharacterBible:
    if not ID_RE.match(char_id or ""):
        raise KeyError(f"캐릭터 id 형식이 아닙니다: {char_id}")
    path = _root(root) / char_id / BIBLE
    if not path.is_file():
        raise KeyError(f"캐릭터가 없습니다: {char_id}")
    return CharacterBible.model_validate_json(path.read_text(encoding="utf-8"))


def save_character(bible: CharacterBible | dict[str, Any], root: Path | None = None) -> CharacterBible:
    bible = CharacterBible.model_validate(bible)
    folder = _root(root) / bible.id
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / (BIBLE + ".tmp")
    tmp.write_text(bible.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(folder / BIBLE)
    return bible


def character_dir(char_id: str, root: Path | None = None) -> Path:
    return _root(root) / char_id


def lock_text(bible: CharacterBible) -> str:
    """캐릭터 외형 고정 문구. 컷마다 똑같이 붙여 얼굴·머리·옷·소품·그림체를 유지한다."""
    if bible.prompt_lock.strip():
        return bible.prompt_lock.strip()
    a, o = bible.appearance, bible.default_outfit
    parts = [
        bible.visual_style or "clean Korean webtoon style, thick clean outlines, flat pastel colors",
        f"the same recurring character named {bible.id}",
        ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in a.items() if v),
        ("wearing " + ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in o.items() if v)) if o else "",
        ("accessories: " + ", ".join(bible.accessories)) if bible.accessories else "",
        "identical face, hairstyle, outfit, accessories and colors in every image",
    ]
    return ". ".join(p for p in parts if p)


def character_prompt(bible: CharacterBible, beat: Any) -> str:
    """AI 이미지 생성 프롬프트. 글자는 넣지 않고 말풍선 자리만 비워 둔다(대사는 렌더러가 합성)."""
    bubble = str(getattr(beat, "speech_bubble_position", "top_right")).replace("_", " ")
    return (f"{lock_text(bible)}. "
            f"Scene: {getattr(beat, 'scene', '')}. Emotion: {getattr(beat, 'emotion', 'neutral')}. "
            f"Pose: {getattr(beat, 'pose', 'standing')}. Camera: {getattr(beat, 'camera', 'medium')} shot. "
            f"Background: {getattr(beat, 'background', '') or 'simple soft background'}. "
            f"Leave clear empty space at the {bubble} for a speech bubble. "
            "Portrait 4:5. No text, no letters, no speech bubbles, no captions, no watermark, no logo.")


def cache_key(bible: CharacterBible, beat: Any) -> str:
    raw = json.dumps([lock_text(bible), getattr(beat, "emotion", ""), getattr(beat, "pose", ""),
                      getattr(beat, "camera", ""), getattr(beat, "background", "")], ensure_ascii=False)
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def reference_for(bible: CharacterBible, emotion: str, pose: str, root: Path | None = None) -> Path | None:
    """Bible 의 reference_images 중 감정·자세가 맞는 파일. 둘 다 맞으면 우선, 감정만 맞아도 사용."""
    folder = character_dir(bible.id, root)
    files = []
    for ref in bible.reference_images:
        p = Path(ref)
        p = p if p.is_absolute() else folder / p
        if p.is_file():
            files.append(p)
    best = [p for p in files if emotion in p.stem.lower() and pose in p.stem.lower()]
    if best:
        return best[0]
    near = [p for p in files if emotion in p.stem.lower()]
    return near[0] if near else None


TORY = {
    "id": "tory_01",
    "name": "토리",
    "role": "경제/부동산 설명 캐릭터",
    "appearance": {"face": "round face, big friendly eyes, rosy cheeks", "skin_tone": "light warm",
                   "hair_style": "chin-length brown bob with straight bangs", "hair_color": "chestnut brown",
                   "eye_color": "dark brown", "age_look": "early 20s"},
    "default_outfit": {"top": "mint green cardigan over white collared shirt", "bottom": "navy skirt"},
    "accessories": ["round black glasses", "small yellow star hairpin"],
    "personality": "차분하고 친절한 설명가. 어려운 말을 쉬운 비유로 바꿔 준다.",
    "speech_style": "~요 체, 짧고 다정하게",
    "visual_style": "clean Korean webtoon style, thick clean outlines, flat pastel colors, chibi proportions",
    "reference_images": [],
    "mascot": {"skin": "#FCE0CC", "hair": "#6B4329", "hair_style": "bob", "eye": "#2B2118",
               "outfit": "#7FD1B9", "outfit_detail": "#FFFFFF", "accessory": "round_glasses",
               "hairpin": "#FFD43B", "cheek": "#FF9AA2"},
}


def ensure_default(root: Path | None = None) -> CharacterBible:
    """기본 캐릭터 토리가 없으면 만든다. 이미 있으면 사용자가 고친 내용을 그대로 둔다."""
    try:
        return get_character(DEFAULT_CHARACTER, root)
    except KeyError:
        return save_character(TORY, root)
