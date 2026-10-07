"""페이지별 그림 고르기.

카드 페이지: 쇼츠의 Source Resolver(source_resolver.resolve)를 그대로 쓴다. 페이지를 '장면'처럼 넘겨
검색 → 권리 판정(CC0·PD·CC BY·NASA 만 usable) → 적합도 평가 → usable 만 내려받기 → 소스 대장 등록.
렌더 직전에 소스 대장으로 다시 확인해, 사용 근거가 없는 파일은 그래픽 카드로 바꾼다.

만화 페이지: ① 업로드 고정 파일(toon_NN_*) ② Character Bible 참고 이미지 ③ AI 생성(설정했을 때, 캐시)
④ 앱이 그리는 마스코트. 각 단계가 실패하면 다음으로 넘어가고, 끝까지 없으면 글자 중심 컷이 된다.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from PIL import Image

from ..pipeline import source_resolver
from ..pipeline.assets import kind_of
from ..pipeline.images import get_images
from ..pipeline.llm import safe_error
from ..pipeline.sources import SourceRegistry
from . import characters as charmod
from .mascot import draw_mascot
from .render import PanelArt
from .schema import CardPage, CarouselPlan, ComicBeat

IMAGE_TYPES = ("cover", "hook", "info_card")
Progress = Callable[[str, int, str], None]


def _scene_view(plan: CarouselPlan) -> SimpleNamespace:
    """Source Resolver 가 읽는 대본 모양(scenes[i].narration / on_screen_text / image_prompt)으로 바꾼다."""
    scenes = []
    for p in plan.pages:
        text = f"{p.headline} {getattr(p, 'body', '') or getattr(p, 'caption', '')}".strip()
        scenes.append(SimpleNamespace(narration=text, on_screen_text=p.headline,
                                      image_prompt=getattr(p, "visual_query", ""), beat_role=""))
    return SimpleNamespace(scenes=scenes)


async def find_card_images(plan: CarouselPlan, *, llm: dict[str, Any], topic: str, work_dir: Path,
                           registry: SourceRegistry, cfg: dict[str, Any], max_images: int = 4,
                           progress: Progress = lambda *a: None) -> tuple[dict[int, dict[str, Any]], dict[str, Any]]:
    """{페이지 index: {path, credit, page_url, reason}}, 보고서. 실패해도 빈 결과로 계속한다."""
    wanted = [i for i, p in enumerate(plan.pages)
              if isinstance(p, CardPage) and p.type in IMAGE_TYPES and p.visual_query.strip()][:max_images]
    if not wanted:
        return {}, {"note": "사진이 필요한 카드가 없습니다"}
    skip = set(range(len(plan.pages))) - set(wanted)
    try:
        found = await source_resolver.resolve(
            llm=llm, script=_scene_view(plan), topic=topic, durations=[4.0] * len(plan.pages), job_dir=work_dir,
            registry=registry, cfg=cfg, profile_spec={"visual_priority": ["image"], "card_roles": []},
            skip=skip, progress=progress)
    except Exception as e:  # noqa: BLE001 - 자료 탐색이 안 되면 그래픽 카드로 만든다
        return {}, {"error": safe_error(e)}
    out = {i: r for i, r in (found.get("scenes") or {}).items() if r.get("kind") == "image"}
    return out, found.get("report") or {}


def guard_image(path: str | Path | None, registry: SourceRegistry) -> bool:
    """화면에 쓸 외부 이미지가 소스 대장에서 사용 가능으로 확인됐는가."""
    if not path or not Path(path).is_file():
        return False
    item = registry.by_path(path)
    return bool(item and item.usable_in_video)


def pinned_uploads(job_dir: Path, registry: SourceRegistry) -> dict[int, Path]:
    """uploads/toon_NN_*.png → 그 페이지(1부터)에 고정. 권리가 확인된 파일만."""
    out: dict[int, Path] = {}
    for f in sorted((job_dir / "uploads").glob("toon_*")) if (job_dir / "uploads").is_dir() else []:
        m = re.match(r"toon_(\d{1,2})_", f.name)
        if m and kind_of(f) == "image" and guard_image(f, registry):
            out.setdefault(int(m.group(1)), f)
    return out


def _has_alpha(img: Image.Image) -> bool:
    if img.mode != "RGBA":
        return False
    lo, _ = img.getchannel("A").getextrema()
    return lo < 250


class CharacterArtist:
    """만화 컷 그림 공급자. 같은 캐릭터·감정·자세는 캐시해 페이지마다 같은 그림을 쓴다."""

    def __init__(self, *, job_dir: Path, registry: SourceRegistry, provider_cfg: dict[str, Any] | None,
                 default_id: str, root: Path | None = None, log: Callable[[str], None] = lambda m: None):
        self.job_dir, self.registry, self.root, self.log = job_dir, registry, root, log
        self.default_id = default_id
        self.provider = None
        if provider_cfg and provider_cfg.get("images", {}).get("provider") not in (None, "", "none"):
            try:
                self.provider = get_images(provider_cfg)
            except Exception as e:  # noqa: BLE001
                log(f"AI 이미지 공급자를 쓸 수 없어 마스코트로 그립니다 ({safe_error(e)})")
        self.bibles: dict[str, charmod.CharacterBible] = {}
        self.ai_failed = False

    def bible(self, char_id: str) -> charmod.CharacterBible | None:
        cid = char_id or self.default_id
        if cid not in self.bibles:
            try:
                self.bibles[cid] = charmod.get_character(cid, self.root)
            except KeyError:
                if cid == self.default_id:
                    return None
                return self.bible(self.default_id)
        return self.bibles[cid]

    async def art(self, beat: ComicBeat, page_no: int, pinned: Path | None = None) -> PanelArt:
        if pinned:
            try:
                img = Image.open(pinned)
                img.load()
                return PanelArt(kind="cutout" if _has_alpha(img.convert("RGBA")) else "scene",
                                image=img.convert("RGBA"), source="upload")
            except Exception as e:  # noqa: BLE001
                self.log(f"{page_no}번 페이지 업로드 그림을 열지 못했습니다 ({e})")
        bible = self.bible(beat.character_id)
        if not bible:
            return PanelArt(kind="none")
        ref = charmod.reference_for(bible, beat.emotion, beat.pose, self.root)
        if ref:
            try:
                img = Image.open(ref).convert("RGBA")
                return PanelArt(kind="cutout" if _has_alpha(img) else "scene", image=img, source="reference")
            except Exception:  # noqa: BLE001
                pass
        if self.provider and not self.ai_failed:
            cache = charmod.character_dir(bible.id, self.root) / "generated" / f"{charmod.cache_key(bible, beat)}.png"
            try:
                if not cache.is_file():
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    await self.provider.generate(charmod.character_prompt(bible, beat), cache, 1080, 1350)
                img = Image.open(cache).convert("RGBA")
                self.registry.add(kind="image", origin="generated", path=str(cache), title=f"{bible.name} 컷",
                                  used_for=f"page_{page_no:02d}")
                return PanelArt(kind="scene", image=img, source="ai_generated")
            except Exception as e:  # noqa: BLE001 - 유료 생성이 실패하면 이번 작업은 마스코트로
                self.ai_failed = True
                self.log(f"AI 캐릭터 생성 실패 - 마스코트로 그립니다 ({safe_error(e)})")
        try:
            return PanelArt(kind="cutout", image=draw_mascot(bible.mascot, beat.emotion, beat.pose), source="mascot")
        except Exception as e:  # noqa: BLE001
            self.log(f"마스코트를 그리지 못했습니다 ({e})")
            return PanelArt(kind="none")

    def guide(self, emotion: str = "happy", pose: str = "pointing") -> Image.Image | None:
        bible = self.bible(self.default_id)
        if not bible:
            return None
        try:
            return draw_mascot(bible.mascot, emotion, pose)
        except Exception:  # noqa: BLE001
            return None
