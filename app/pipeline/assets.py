"""첨부 파일 관리 + 장면별 비주얼 결정.

비주얼 우선순위: 첨부 파일 → 링크에서 수집한 이미지 → AI 생성 → 단색 카드
"""
from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path
from typing import Any

from .media import extract_frames, probe_duration
from .models import Asset, Scene, SceneVisual, SourcedImage
from .vision import describe_all, match_assets_to_scenes, vision_available

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}


def kind_of(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    return None


async def load_assets(upload_dir: Path, log=print) -> list[Asset]:
    """업로드 폴더를 훑어 Asset 목록을 만든다. 영상은 대표 프레임도 뽑는다."""
    if not upload_dir.exists():
        return []
    frames_dir = upload_dir / "_frames"
    assets: list[Asset] = []
    for p in sorted(upload_dir.iterdir()):
        if p.is_dir() or p.name.startswith("_"):
            continue
        k = kind_of(p)
        if not k:
            continue
        a = Asset(path=str(p), kind=k, name=p.name)
        if k == "video":
            try:
                a.duration = await probe_duration(p)
                frames = await extract_frames(p, frames_dir, count=1)
                if frames:
                    a.preview = str(frames[0])
            except Exception as e:  # noqa: BLE001
                log(f"{p.name} 정보를 읽지 못했습니다: {e}")
        else:
            a.preview = str(p)
        assets.append(a)
    if assets:
        log(f"첨부 파일 {len(assets)}개 (사진 {sum(1 for a in assets if a.kind == 'image')}, "
            f"영상 {sum(1 for a in assets if a.kind == 'video')})")
    return assets


async def describe_assets(assets: list[Asset], log=print) -> None:
    """각 첨부의 내용을 비전으로 설명해 Asset.description 에 채운다 (제자리 수정)."""
    if not assets:
        return
    previews = [Path(a.preview) for a in assets if a.preview]
    if not previews:
        return
    descs = await describe_all(previews, log=log)
    it = iter(descs)
    for a in assets:
        if not a.preview:
            continue
        d = next(it, None)
        if d:
            a.description = d.description


# scene_03_flow.png / scene-7-a.jpg / scene00.mp4 을 모두 잡는다.
# \b 를 쓰면 'scene_03_flow' 처럼 숫자 뒤에 밑줄이 오는 경우를 놓친다 (숫자와 _ 는 둘 다 단어문자).
SCENE_PIN = re.compile(r"^scene[_-]?(\d{1,2})(?!\d)", re.I)


def pinned_scene(name: str) -> int | None:
    """scene_03_xxx.jpg 처럼 장면을 직접 지정한 파일명이면 그 번호(0부터)."""
    m = SCENE_PIN.match(Path(name).stem)
    return int(m.group(1)) if m else None


async def plan_assets(llm: dict[str, Any], assets: list[Asset], scenes: list[Scene],
                      log=print) -> dict[int, Asset]:
    """장면 번호 → 첨부 파일.

    파일명으로 장면을 지정한 것(scene_03_*)이 최우선이고, 나머지를 비전으로 배치한다.
    비전을 못 쓰면 남은 자리에 올린 순서대로 넣는다.
    """
    if not assets:
        return {}

    # 1) 파일명으로 장면이 고정된 것 먼저 (Flow 에서 만든 이미지를 장면별로 올릴 때)
    out: dict[int, Asset] = {}
    rest: list[Asset] = []
    for a in assets:
        idx = pinned_scene(a.name)
        if idx is not None and 0 <= idx < len(scenes) and idx not in out:
            out[idx] = a
        else:
            rest.append(a)
    if out:
        log(f"파일명으로 지정된 장면 {len(out)}개")
    if not rest:
        return out

    assets = rest
    free = [i for i in range(len(scenes)) if i not in out]

    def in_order() -> dict[int, Asset]:
        return {**out, **{s: a for s, a in zip(free, assets)}}

    if not vision_available():
        log("내용 분석 없이 올린 순서대로 배치합니다")
        return in_order()

    try:
        plan = await match_assets_to_scenes(llm, assets, scenes, log=log)
    except Exception as e:  # noqa: BLE001
        log(f"배치 분석 실패 - 올린 순서대로 배치합니다 ({e})")
        return in_order()

    for m in sorted(plan.matches, key=lambda x: -x.fit):   # 적합도 높은 것부터 자리 차지
        if not (0 <= m.asset_index < len(assets)):
            continue
        if not (0 <= m.scene_index < len(scenes)) or m.fit < 3:
            continue
        if m.scene_index in out:
            continue
        out[m.scene_index] = assets[m.asset_index]
    return out


def plan_sourced(images: list[SourcedImage], scenes: list[Scene],
                 taken: set[int]) -> dict[int, SourcedImage]:
    """수집 이미지를 아직 비어 있는 장면에 앞에서부터 채운다.

    og:image 가 맨 앞이라 대표성이 높은 순서대로 들어간다.
    """
    out: dict[int, SourcedImage] = {}
    pool = list(images)
    for i in range(len(scenes)):
        if i in taken or not pool:
            continue
        out[i] = pool.pop(0)
    return out


async def resolve_visuals(llm: dict[str, Any], scenes: list[Scene], assets: list[Asset],
                          sourced: list[SourcedImage], log=print) -> list[SceneVisual]:
    """장면마다 어떤 비주얼을 쓸지 정한다. 생성이 필요한 장면은 kind='generated' 로 남긴다."""
    by_scene = await plan_assets(llm, assets, scenes, log=log)
    src_map = plan_sourced(sourced, scenes, set(by_scene))

    visuals: list[SceneVisual] = []
    for i in range(len(scenes)):
        if i in by_scene:
            a = by_scene[i]
            visuals.append(SceneVisual(scene_index=i, kind="upload", path=a.path,
                                       note=f"첨부 {a.name}"))
        elif i in src_map:
            s = src_map[i]
            visuals.append(SceneVisual(scene_index=i, kind="sourced", path=s.path,
                                       credit=s.credit(), note=f"{s.site} 기사 이미지"))
        else:
            visuals.append(SceneVisual(scene_index=i, kind="generated", note="AI 생성 예정"))

    counts = {k: sum(1 for v in visuals if v.kind == k) for k in ("upload", "sourced", "generated")}
    log(f"비주얼 배치 - 첨부 {counts['upload']} / 기사 {counts['sourced']} / 생성 {counts['generated']}")
    return visuals


def save_upload(job_dir: Path, filename: str, data: bytes) -> Path | None:
    """업로드 파일 1개 저장. 지원하지 않는 형식이면 None."""
    safe = Path(filename).name.replace("\\", "_")
    if kind_of(Path(safe)) is None:
        return None
    d = job_dir / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    out = d / safe
    n = 2
    while out.exists():
        out = d / f"{Path(safe).stem}_{n}{Path(safe).suffix}"
        n += 1
    out.write_bytes(data)
    return out


def move_uploads(src_dir: Path, job_dir: Path) -> int:
    """임시 업로드 폴더의 파일을 잡 폴더로 옮긴다."""
    if not src_dir.exists():
        return 0
    dst = job_dir / "uploads"
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in src_dir.iterdir():
        if p.is_file() and kind_of(p):
            shutil.move(str(p), str(dst / p.name))
            n += 1
    shutil.rmtree(src_dir, ignore_errors=True)
    return n
