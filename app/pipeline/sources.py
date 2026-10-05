"""잡별 소스 권리 대장과 렌더/내보내기 전 검사. 기본값은 사용 불가."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from .models import SourceItem

FILE = "sources.json"
PROVEN_LICENSES = {"my_channel", "licensed_upload", "ai_generated", "pexels", "pixabay", "kogl_type0", "kogl_type1",
                   # Source Resolver 가 라이선스 메타데이터로 자동 판정한 공개 자료 (상업 이용·변형 허용)
                   "cc0", "public_domain", "cc_by", "nasa_media"}
ATTRIBUTION_LICENSES = {"pexels", "pixabay", "kogl_type0", "kogl_type1", "cc_by"}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _key(path: str = "", url: str = "") -> str:
    value = str(Path(path).resolve()) if path else url.strip()
    return "src-" + hashlib.sha256(value.encode()).hexdigest()[:12]


def _usable(item: SourceItem) -> bool:
    if item.origin == "generated" and item.license == "ai_generated":
        return True  # 앱이 만든 출력물. 외부 입력 파일에는 적용하지 않는다.
    if item.license not in PROVEN_LICENSES:
        return False
    if not (item.rights_confirmed and item.commercial_allowed and item.adaptation_allowed
            and item.third_party_rights_checked and item.license_checked_at):
        return False
    if item.license in ATTRIBUTION_LICENSES:
        return item.license_url.startswith(("https://", "http://")) and bool(item.credit)
    return bool(item.license_url.startswith(("https://", "http://")) or item.license_note.strip())


class SourceRegistry:
    def __init__(self, job_dir: Path):
        self.job_dir = job_dir
        self.path = job_dir / FILE
        self.items: dict[str, SourceItem] = {}
        if self.path.exists():
            for raw in json.loads(self.path.read_text(encoding="utf-8")):
                item = SourceItem.model_validate(raw)
                item.usable_in_video = _usable(item)
                self.items[item.id] = item

    def save(self) -> None:
        self.job_dir.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".json.tmp")
        temp.write_text(json.dumps([x.model_dump() for x in self.items.values()], ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def add(self, *, kind: str, origin: str, path: str = "", url: str = "", title: str = "",
            rights: dict[str, Any] | None = None, used_for: str = "", parent_id: str = "",
            source_type: str = "", usage: str = "", rights_status: str = "", rights_basis: str = "") -> SourceItem:
        rights = rights or {}
        key = _key(path, url)
        old = self.items.get(key)
        item = SourceItem(
            id=key, kind=kind, origin=origin, path=path, url=url, title=title, parent_id=parent_id,
            license="ai_generated" if origin == "generated" else str(rights.get("license") or ("reference_only" if origin == "url" else "unknown")),
            license_url=str(rights.get("license_url") or ""),
            license_checked_at=_now() if rights.get("rights_confirmed") or origin == "generated" else "",
            commercial_allowed=bool(rights.get("commercial_allowed")),
            adaptation_allowed=bool(rights.get("adaptation_allowed")),
            third_party_rights_checked=bool(rights.get("third_party_rights_checked")),
            rights_confirmed=bool(rights.get("rights_confirmed")),
            credit=str(rights.get("credit") or ""), license_note=str(rights.get("license_note") or ""),
            used_for=list(dict.fromkeys([*(old.used_for if old else []), *([used_for] if used_for else [])])),
            retrieved_at=old.retrieved_at if old else _now(),
            source_type=source_type or str(rights.get("source_type") or (old.source_type if old else "")),
            usage=usage or (old.usage if old else ""),
            rights_basis=rights_basis or str(rights.get("rights_basis") or (old.rights_basis if old else "")),
            scene_ids=old.scene_ids if old else [], clip_ranges=old.clip_ranges if old else [],
        )
        item.usable_in_video = _usable(item)
        # 권리 상태는 계산 결과를 우선한다. 호출 쪽이 usable 이라고 해도 근거가 부족하면 낮춘다.
        status = rights_status or str(rights.get("rights_status") or "")
        if item.usable_in_video:
            item.rights_status = "usable"
        elif status in ("reference_only", "unknown"):
            item.rights_status = status
        else:
            item.rights_status = "reference_only" if origin == "url" else "unknown"
        if not item.usage:
            item.usage = ("research" if used_for in ("script_research",) else
                          "reference_only" if not item.usable_in_video else "")
        self.items[key] = item
        self.save()
        return item

    def mark_used(self, path: str | Path, scene_number: int, clip_range: str = "") -> None:
        """화면에 실제로 쓴 소스에 장면 번호(1부터)와 영상 구간을 남긴다. 가공본이면 원본에도 남긴다."""
        item = self.by_path(path)
        seen: set[str] = set()
        while item and item.id not in seen:
            seen.add(item.id)
            item.usage = "visual"
            if scene_number not in item.scene_ids:
                item.scene_ids.append(scene_number)
            if clip_range and clip_range not in item.clip_ranges:
                item.clip_ranges.append(clip_range)
            item = self.items.get(item.parent_id) if item.parent_id else None
        self.save()

    def by_path(self, path: str | Path) -> SourceItem | None:
        return self.items.get(_key(str(path)))

    def by_url(self, url: str) -> SourceItem | None:
        return self.items.get(_key(url=url))

    def relocate(self, old_path: Path, new_path: Path) -> None:
        item = self.items.pop(_key(str(old_path)), None)
        if item:
            item.path = str(new_path)
            item.id = _key(str(new_path))
            self.items[item.id] = item
            self.save()

    def remove_path(self, path: Path) -> None:
        if self.items.pop(_key(str(path)), None):
            self.save()

    def guard_timeline(self, tl: dict[str, Any]) -> None:
        if not self.path.exists():
            raise ValueError("이 작업에는 소스 사용 권한 대장이 없습니다. 기존 영상의 권리를 확인한 뒤 새 작업으로 제작해 주세요.")
        paths = [tl.get("narration", ""), tl.get("bgm", "")]
        paths += [s.get("visual", {}).get("path", "") for s in tl.get("scenes", [])]
        paths += [c.get("path", "") for c in tl.get("comments", []) if c.get("kind") == "image"]
        for value in filter(None, paths):
            path = Path(value)
            if not path.is_absolute():
                path = self.job_dir / path
            item = self.by_path(path)
            if not item or not item.usable_in_video:
                raise ValueError(f"렌더링/내보내기 중단: '{path.name}'의 영상 사용 권한이 확인되지 않았습니다. 소스 대장을 확인해 주세요.")
        for c in tl.get("comments", []):
            if c.get("kind") == "text":
                raise ValueError("타인 댓글 원문은 영상에 사용할 수 없습니다. 댓글을 제거해 주세요.")


def guard_timeline(job_dir: Path, tl: dict[str, Any]) -> None:
    SourceRegistry(job_dir).guard_timeline(tl)
