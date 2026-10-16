"""사용자 그림 받은편지함 — ChatGPT 등에서 직접 만든 배경·캐릭터 그림을 assets/inbox/ 에 넣으면 자동 등록한다 (무료).

파일 이름 규칙 (밑줄로 구분, 한글 가능):
  배경:   bg_<장소 단어들>.png          예) bg_원룸_밤.png, bg_마트_계산대.png, bg_은행_창구.png
  캐릭터: <캐릭터>_<감정>_<자세>.png     예) 햄토리치_놀람_서있음.png, hamtorich_01_happy_pointing.png,
                                          다람_걱정_지갑.png (처음 보는 이름이면 새 조연 캐릭터로 만든다)
감정: 기본 행복 놀람 걱정 생각 자신감 슬픔 화남 (또는 영어 neutral happy surprised worried thinking confident sad angry)
배경이 흰색인 캐릭터 그림은 흰 배경을 지워 투명 PNG 로 만든다. 처리한 원본은 inbox/_done/<날짜>/ 로 옮긴다.
이름으로 분류할 수 없는 파일은 그대로 두고 이유를 알려 준다 (지우지 않는다).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import shutil
from pathlib import Path
from typing import Any

from PIL import Image

from . import characters as charmod
from .backgrounds import BG_ROOT, load_index, save_index

INBOX = Path(__file__).resolve().parents[2] / "assets" / "inbox"
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
EMOTIONS = {"기본": "neutral", "보통": "neutral", "행복": "happy", "기쁨": "happy", "웃음": "happy", "놀람": "surprised",
            "걱정": "worried", "불안": "worried", "생각": "thinking", "고민": "thinking", "자신감": "confident",
            "뿌듯": "confident", "슬픔": "sad", "눈물": "sad", "화남": "angry", "분노": "angry"}
EN_EMOTIONS = ("neutral", "happy", "surprised", "worried", "thinking", "confident", "sad", "angry")
POSES = {"서있음": "standing", "기본": "standing", "가리킴": "pointing", "설명": "explaining", "손흔듦": "waving",
         "팔짱": "arms_crossed", "턱": "chin", "만세": "cheering", "어깨": "shrug", "달리기": "running", "앉음": "sitting"}
NIGHT, SUNSET, GLOOMY = ("밤", "야근", "새벽", "야경"), ("노을", "저녁", "퇴근길"), ("비", "우울")
SOURCE = "사용자 제작 (ChatGPT 등) — 사용자가 직접 만들어 넣은 그림"


def _character_by_name(name: str, root: Path | None) -> charmod.CharacterBible | None:
    for bible in charmod.list_characters(root):
        if name in (bible.id, bible.name) or bible.id.startswith(name.lower() + "_"):
            return bible
    return None


def _has_transparency(img: Image.Image) -> bool:
    return img.mode in ("RGBA", "LA") and img.getchannel("A").getextrema()[0] < 250


def _white_border(img: Image.Image) -> bool:
    rgb = img.convert("RGB")
    w, h = rgb.size
    border = [rgb.getpixel((x, 0)) for x in range(0, w, max(1, w // 20))] + [rgb.getpixel((0, y)) for y in range(0, h, max(1, h // 20))]
    return sum(min(p) >= 235 for p in border) / len(border) > 0.85


def _background(path: Path, words: list[str], bg_root: Path | None) -> dict[str, Any]:
    from .render import cover_fit
    folder = bg_root or BG_ROOT
    folder.mkdir(parents=True, exist_ok=True)
    tags = [w for w in words if w]
    key = "user_" + hashlib.md5(" ".join(tags).encode()).hexdigest()[:8]
    out = folder / f"{key}.png"
    n = 2
    while out.exists():
        out = folder / f"{key}_{n}.png"
        n += 1
    img = Image.open(path).convert("RGB")
    # 가로·정사각 배경도 세로 4:5 로 가운데를 잘라 쓴다 (원본은 _done 에 남는다)
    cover_fit(img, 1080, 1350).save(out, optimize=True)
    text = " ".join(tags)
    mood = "night" if any(w in text for w in NIGHT) else "sunset" if any(w in text for w in SUNSET) else \
        "gloomy" if any(w in text for w in GLOOMY) else "day"
    index = load_index(bg_root)
    # 태그에 '밤' 같은 시간 단어만 있으면 장소 매칭이 안 되므로, 장소 단어는 그대로 태그로 쓴다
    index.append({"id": out.stem, "file": out.name, "tags": tags + [" ".join(tags)], "mood": mood, "approved": True,
                  "source": SOURCE, "original": path.name})
    save_index(index, bg_root)
    return {"kind": "background", "file": str(out), "tags": tags, "mood": mood}


def _pose(path: Path, words: list[str], root: Path | None) -> dict[str, Any]:
    from .asset_gen import remove_white_background
    name, rest = words[0], words[1:]
    if name.lower() == "hamtorich" and rest and rest[0] == "01":
        name, rest = "hamtorich_01", rest[1:]
    emotion = next((EMOTIONS.get(w) or (w if w in EN_EMOTIONS else None) for w in rest
                    if EMOTIONS.get(w) or w in EN_EMOTIONS), None)
    if not emotion:
        raise ValueError(f"감정 단어가 없습니다 (예: {name}_놀람_서있음.png)")
    pose_words = [w for w in rest if not (EMOTIONS.get(w) or w in EN_EMOTIONS)]
    pose = POSES.get(pose_words[0], pose_words[0].lower()) if pose_words else "standing"
    bible = _character_by_name(name, root)
    if bible is None:
        cid = "cast_" + hashlib.md5(name.encode()).hexdigest()[:6]
        bible = charmod.save_character(charmod.CharacterBible(
            id=cid, name=name, role="사용자가 등록한 조연 캐릭터", visual_style="햄토리치 마스터 시트와 같은 그림체로 맞춘다",
            mascot_fallback=False, rights="owned",
            design_rules=["처음 등록한 포즈를 이 캐릭터의 기준으로 삼는다", "투명 배경, 글자 없음"]), root)
    img = Image.open(path)
    note = []
    if _has_transparency(img):
        out_img = img.convert("RGBA")
    elif _white_border(img):
        out_img = remove_white_background(img)
        note.append("흰 배경을 지워 투명 PNG 로 변환")
    else:
        raise ValueError("배경이 있는 캐릭터 그림입니다. 투명 PNG 또는 흰 배경으로 다시 만들어 주세요")
    folder = charmod.character_dir(bible.id, root) / "poses"
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"user_{emotion}_{pose}"
    out = folder / f"{stem}.png"
    n = 2
    while out.exists():
        out = folder / f"{stem}_{n}.png"
        n += 1
    out_img.save(out, optimize=True)
    rel = f"poses/{out.name}"
    bible.poses.append(charmod.PoseAsset(file=rel, emotion=emotion, pose=pose, description=f"사용자 등록: {path.name}",
                                         differences=[SOURCE] + note, approved=True))
    if not bible.default_pose:
        bible.default_pose = rel
    charmod.save_character(bible, root)
    return {"kind": "pose", "character": bible.id, "file": str(out), "emotion": emotion, "pose": pose, "notes": note}


def import_inbox(*, inbox: Path | None = None, root: Path | None = None, bg_root: Path | None = None) -> dict[str, Any]:
    folder = inbox or INBOX
    folder.mkdir(parents=True, exist_ok=True)
    done_dir = folder / "_done" / dt.date.today().isoformat()
    added, skipped = [], []
    for path in sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXT):
        words = [w for w in re.split(r"[_\s]+", path.stem) if w]
        try:
            if not words:
                raise ValueError("파일 이름이 비어 있습니다")
            if words[0].lower() in ("bg", "배경"):
                if len(words) < 2:
                    raise ValueError("배경 장소 단어가 없습니다 (예: bg_원룸_밤.png)")
                added.append(_background(path, words[1:], bg_root))
            else:
                added.append(_pose(path, words, root))
            done_dir.mkdir(parents=True, exist_ok=True)
            archived = done_dir / path.name
            n = 2
            while archived.exists():
                archived = done_dir / f"{path.stem}_{n}{path.suffix}"
                n += 1
            shutil.move(str(path), archived)
        except Exception as e:  # noqa: BLE001 - 한 파일 문제로 나머지를 멈추지 않는다
            skipped.append({"file": path.name, "reason": str(e)[:200]})
    return {"status": "ok", "added": added, "skipped": skipped, "inbox": str(folder),
            "rules": "배경 bg_<장소>_<시간>.png · 캐릭터 <이름>_<감정>_<자세>.png"}
