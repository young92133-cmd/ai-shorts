"""CapCut 으로 내보내기.

1) export_draft: CapCut 데스크톱 드래프트 폴더에 새 프로젝트를 만든다. 장면·나레이션·BGM·자막·키워드·
   댓글이 각각 따로 된 트랙으로 들어가 CapCut 에서 하나씩 고칠 수 있다.
2) export_pack: 재료 묶음 zip (장면 파일·음성·SRT 자막·댓글 캡처·순서표). CapCut 드래프트 형식이
   바뀌어도 이 방법은 계속 쓸 수 있다.

드래프트 JSON 은 CapCut 이 실제로 불러들여 다시 저장한 스크립트 생성 드래프트(draft_info.json,
version 360000)의 최소 키 구성을 따른다. 시간 단위는 마이크로초(µs).
위치 좌표(clip.transform)는 화면 가운데가 0, 반 화면 폭/높이가 1 이며 위쪽이 + 이다.

기존 드래프트나 CapCut 의 목록 파일(root_meta_info.json)은 건드리지 않는다. 새 폴더만 만든다.
CapCut 을 켜 둔 상태였다면 껐다 켜야 목록에 보인다.
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import re
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any

from .media import probe_duration, probe_video, run_ffmpeg
from .subtitles import write_srt
from .timeline import resolve, total_duration

US = 1_000_000
PHOTO_DURATION = 10_800_000_000   # CapCut 이 사진을 가져올 때 쓰는 소재 길이(3시간)

# 소재 목록의 모든 칸. 쓰지 않는 칸도 빈 목록으로 있어야 한다.
MATERIAL_KEYS = (
    "ai_translates", "audio_balances", "audio_effects", "audio_fades", "audio_pannings", "audio_pitch_shifts",
    "audio_track_indexes", "audios", "beats", "canvases", "chromas", "color_curves", "common_mask",
    "digital_humans", "drafts", "effects", "flowers", "green_screens", "handwrites", "hsl", "hsl_curves",
    "images", "log_color_wheels", "loudnesses", "manual_beautys", "manual_deformations", "material_animations",
    "material_colors", "multi_language_refs", "placeholder_infos", "placeholders", "plugin_effects",
    "primary_color_wheels", "realtime_denoises", "shapes", "smart_crops", "smart_relights",
    "sound_channel_mappings", "speeds", "stickers", "tail_leaders", "text_templates", "texts", "time_marks",
    "transitions", "video_effects", "video_radius", "video_shadows", "video_strokes", "video_trackings",
    "videos", "vocal_beautifys", "vocal_separations",
)

_SEGMENT_BASE: dict[str, Any] = {
    "caption_info": None, "cartoon": False, "desc": "", "enable_adjust": True,
    "enable_color_correct_adjust": False, "enable_color_curves": True, "enable_color_wheels": True,
    "enable_lut": True, "enable_smart_color_adjust": False, "enable_video_mask": True, "group_id": "",
    "hdr_settings": {"intensity": 1, "mode": 1, "nits": 1000}, "is_loop": False, "is_placeholder": False,
    "last_nonzero_volume": 1, "reverse": False,
    "responsive_layout": {"enable": False, "horizontal_pos_layout": 0, "size_layout": 0,
                          "target_follow": "", "vertical_pos_layout": 0},
    "source": "segmentsourcenormal", "state": 0, "template_id": "", "template_scene": "default",
    "track_attribute": 0, "track_render_index": 0, "visible": True, "common_keyframes": [], "keyframe_refs": [],
    "speed": 1, "volume": 1, "render_timerange": {"start": 0, "duration": 0}, "render_index": 0,
}

_TEXT_BASE: dict[str, Any] = {
    "add_type": 0, "alignment": 1, "background_alpha": 1, "background_color": "", "background_fill": "",
    "background_height": 0.14, "background_horizontal_offset": 0, "background_round_radius": 0,
    "background_style": 0, "background_vertical_offset": 0, "background_width": 0.14, "base_content": "",
    "bold_width": 0, "border_alpha": 1, "border_color": "#000000", "border_mode": 0, "border_width": 0.08,
    "caption_template_info": {"category_id": "", "category_name": "", "effect_id": "", "is_new": False,
                              "path": "", "request_id": "", "resource_id": "", "resource_name": "",
                              "source_platform": 0},
    "check_flag": 31, "combo_info": {"text_templates": []}, "fixed_height": -1, "fixed_width": -1,
    "font_category_id": "", "font_category_name": "", "font_id": "", "font_resource_id": "",
    "font_source_platform": 0, "font_team_id": "", "font_url": "", "fonts": [],
    "force_apply_line_max_width": False, "global_alpha": 1, "group_id": "", "has_shadow": False,
    "initial_scale": 1, "inner_padding": -1, "is_rich_text": False, "italic_degree": 0, "ktv_color": "",
    "language": "", "layer_weight": 1, "letter_spacing": 0, "line_feed": 1, "line_max_width": 0.82,
    "line_spacing": 0.02, "multi_language_current": "none", "name": "", "original_size": [],
    "preset_category": "", "preset_category_id": "", "preset_has_set_alignment": False, "preset_id": "",
    "preset_index": 0, "preset_name": "", "recognize_task_id": "", "recognize_type": 0,
    "relevance_segment": [], "shadow_alpha": 0.9, "shadow_angle": -45, "shadow_color": "",
    "shadow_distance": 0.04, "shadow_point": {"x": 0.64, "y": 0.64}, "shadow_smoothing": 0.45,
    "shape_clip_x": False, "shape_clip_y": False, "source_from": "", "style_name": "", "sub_type": 0,
    "subtitle_keywords": None, "subtitle_template_original_fontsize": 0, "text_alpha": 1,
    "text_color": "#ffffff", "text_curve": None, "text_preset_resource_id": "", "text_to_audio_ids": [],
    "tts_auto_update": False, "typesetting": 0, "underline": False, "underline_offset": 0.22,
    "underline_width": 0.05, "use_effect_default_color": False,
    "words": {"end_time": [], "start_time": [], "text": []},
}

_PLATFORM = {"app_id": 359289, "app_source": "cc", "app_version": "", "device_id": "", "hard_disk_id": "",
             "mac_address": "", "os": "windows", "os_version": ""}


def _uid() -> str:
    return str(uuid.uuid4()).upper()


def _us(sec: float) -> int:
    return int(round(float(sec) * US))


def _rgb(hex_color: str) -> list[float]:
    h = hex_color.lstrip("#")
    return [round(int(h[i:i + 2], 16) / 255, 4) for i in (0, 2, 4)]


def _utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


# ---------- 드래프트 폴더 ----------

def find_drafts_root(cfg: dict[str, Any] | None = None) -> Path | None:
    """CapCut 이 새 프로젝트를 저장하는 폴더.

    config.yaml capcut.drafts_dir → CapCut 설정의 사용자 지정 경로(currentCustomDraftPath) → 기본 위치.
    """
    custom = ((cfg or {}).get("capcut") or {}).get("drafts_dir")
    if custom:
        return Path(custom)
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "CapCut" / "User Data"
    setting = base / "Config" / "globalSetting"
    try:
        for line in setting.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("currentCustomDraftPath="):
                value = line.split("=", 1)[1].strip().replace("\\\\", "\\")
                if value and Path(value).is_dir():
                    return Path(value)
    except OSError:
        pass
    default = base / "Projects" / "com.lveditor.draft"
    return default if default.is_dir() else None


def safe_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", name).strip(" .")
    return re.sub(r"\s+", " ", name)[:60] or "AI 쇼츠"


def _unique_dir(root: Path, name: str) -> Path:
    out, n = root / name, 2
    while out.exists():
        out = root / f"{name}_{n}"
        n += 1
    return out


# ---------- 소재·세그먼트 ----------

class _Draft:
    def __init__(self, width: int, height: int, fps: int) -> None:
        self.width, self.height, self.fps = width, height, fps
        self.materials: dict[str, list[dict[str, Any]]] = {k: [] for k in MATERIAL_KEYS}
        self.tracks: list[dict[str, Any]] = []
        self._media: dict[str, str] = {}

    def _helper(self, kind: str, **fields: Any) -> str:
        mid = _uid()
        if kind == "speeds":
            self.materials["speeds"].append({"curve_speed": None, "id": mid, "mode": 0, "speed": 1, "type": "speed"})
        else:   # canvases
            self.materials["canvases"].append({"album_image": "", "blur": 0, "color": "", "id": mid, "image": "",
                                               "image_id": "", "image_name": "", "source_platform": 0,
                                               "team_id": "", "type": "canvas_color", **fields})
        return mid

    def media(self, path: Path, kind: str, duration_us: int, width: int, height: int, has_audio: bool) -> str:
        key = f"{kind}:{path}"
        if key in self._media:
            return self._media[key]
        mid = _uid()
        self.materials["videos"].append({
            "aigc_type": "none", "audio_fade": None, "category_id": "", "category_name": "local",
            "check_flag": 1,
            "crop": {"lower_left_x": 0, "lower_left_y": 1, "lower_right_x": 1, "lower_right_y": 1,
                     "upper_left_x": 0, "upper_left_y": 0, "upper_right_x": 1, "upper_right_y": 0},
            "crop_ratio": "free", "crop_scale": 1, "duration": duration_us, "extra_type_option": 0,
            "formula_id": "", "freeze": None, "has_audio": has_audio, "height": height, "id": mid,
            "is_ai_generate_content": False, "is_copyright": False, "is_unified_beauty_mode": False,
            "local_id": "", "local_material_from": "", "local_material_id": str(uuid.uuid4()),
            "material_id": "", "material_name": path.name, "material_url": "",
            "matting": {"flag": 0, "has_use_quick_brush": False, "has_use_quick_eraser": False,
                        "interactiveTime": [], "path": "", "strokes": []},
            "media_path": "", "object_locked": None, "origin_material_id": "", "path": str(path),
            "picture_from": "none", "request_id": "", "reverse_path": "", "source": 0, "source_platform": 0,
            "stable": {"matrix_path": "", "stable_level": 0, "time_range": {"duration": 0, "start": 0}},
            "team_id": "", "type": kind,
            "video_algorithm": {"algorithms": [], "path": ""}, "width": width,
        })
        self._media[key] = mid
        return mid

    def audio(self, path: Path, duration_us: int) -> str:
        mid = _uid()
        self.materials["audios"].append({
            "app_id": 0, "category_id": "", "category_name": "local", "check_flag": 1, "duration": duration_us,
            "effect_id": "", "formula_id": "", "id": mid, "intensifies_path": "", "is_ugc": False,
            "local_material_id": str(uuid.uuid4()), "name": path.name, "path": str(path), "request_id": "",
            "resource_id": "", "search_id": "", "source_from": "", "source_platform": 0, "team_id": "",
            "text_id": "", "type": "extract_music", "wave_points": [],
        })
        return mid

    def text(self, text: str, *, size: float, color: str = "#FFFFFF", stroke: str = "#000000",
             font_path: str = "", background: str = "", kind: str = "text") -> str:
        mid = _uid()
        style: dict[str, Any] = {
            "fill": {"alpha": 1, "content": {"render_type": "solid", "solid": {"alpha": 1, "color": _rgb(color)}}},
            "strokes": [{"width": 0.08, "mode": 0,
                         "content": {"render_type": "solid", "solid": {"color": _rgb(stroke)}}}] if stroke else [],
            "useLetterColor": True, "range": [0, _utf16_len(text)], "size": size, "bold": True,
            "italic": False, "underline": False, "font": {"id": "", "path": font_path},
        }
        mat = copy.deepcopy(_TEXT_BASE)
        mat.update({
            "id": mid, "type": kind, "content": json.dumps({"styles": [style], "text": text}, ensure_ascii=False),
            "font_path": font_path, "font_name": "", "font_title": "", "font_size": size, "text_size": size,
            "text_color": color.lower(), "border_color": stroke or "", "border_width": 0.08 if stroke else 0,
        })
        if background:
            mat.update(background_style=1, background_color=background, background_alpha=1,
                       background_round_radius=0.2, background_width=0.14, background_height=0.14)
        self.materials["texts"].append(mat)
        return mid

    def track(self, kind: str, segments: list[dict[str, Any]]) -> None:
        if not segments:
            return
        index = len(self.tracks)
        for s in segments:
            s["track_render_index"] = index
        self.tracks.append({"attribute": 0, "flag": 0, "id": _uid(), "is_default_name": True, "name": "",
                            "type": kind, "segments": segments})

    def segment(self, material_id: str, start: float, dur: float, *, src_start: float = 0.0,
                volume: float = 1.0, visual: bool = True, x: float = 0.0, y: float = 0.0,
                scale: float = 1.0, canvas: bool = False, text: bool = False) -> dict[str, Any]:
        seg = copy.deepcopy(_SEGMENT_BASE)
        refs = [] if text else [self._helper("speeds")]
        if canvas:
            refs.append(self._helper("canvases"))
        seg.update({
            "id": _uid(), "material_id": material_id,
            "target_timerange": {"start": _us(start), "duration": _us(dur)},
            "source_timerange": {"start": _us(src_start), "duration": _us(dur)},
            "volume": volume, "extra_material_refs": refs,
            "clip": {"alpha": 1, "flip": {"horizontal": False, "vertical": False}, "rotation": 0,
                     "scale": {"x": scale, "y": scale}, "transform": {"x": round(x, 5), "y": round(y, 5)}}
            if visual else None,
            "uniform_scale": {"on": True, "value": 1} if visual else None,
        })
        if not visual:
            seg.update(enable_adjust=False, enable_lut=False, hdr_settings=None)
        return seg

    def content(self, name: str, duration_us: int) -> dict[str, Any]:
        now = int(time.time())
        return {
            "canvas_config": {"background": None, "height": self.height, "ratio": "9:16", "width": self.width},
            "color_space": 0,
            "config": {"adjust_max_index": 1, "attachment_info": [], "combination_max_index": 1,
                       "export_range": None, "extract_audio_last_index": 1, "lyrics_recognition_id": "",
                       "lyrics_sync": True, "lyrics_taskinfo": [], "maintrack_adsorb": True,
                       "material_save_mode": 0, "multi_language_current": "none", "multi_language_list": [],
                       "multi_language_main": "none", "multi_language_mode": "none",
                       "original_sound_last_index": 1, "record_audio_last_index": 1, "sticker_max_index": 1,
                       "subtitle_keywords_config": None, "subtitle_recognition_id": "", "subtitle_sync": True,
                       "subtitle_taskinfo": [], "system_font_list": [], "use_float_render": False,
                       "video_mute": False, "zoom_info_params": None},
            "cover": None, "create_time": now, "draft_type": "video", "duration": duration_us,
            "extra_info": None, "fps": self.fps, "free_render_index_mode_on": False,
            "function_assistant_info": {"auto_adjust": False, "auto_caption": False, "caption_opt": False,
                                        "color_correction": False, "enhance_quality": False,
                                        "fps": {"den": 1, "num": 0}, "normalize_loudness": False,
                                        "retouch": False},
            "group_container": None, "id": _uid(), "is_drop_frame_timecode": False, "keyframe_graph_list": [],
            "keyframes": {"adjusts": [], "audios": [], "effects": [], "filters": [], "handwrites": [],
                          "stickers": [], "texts": [], "videos": []},
            "last_modified_platform": dict(_PLATFORM), "lyrics_effects": [], "materials": self.materials,
            "mutable_config": None, "name": name, "new_version": "161.0.0", "path": "",
            "platform": dict(_PLATFORM), "relationships": [], "render_index_track_mode_on": True,
            "retouch_cover": None, "source": "default", "static_cover_image_path": "", "time_marks": None,
            "tracks": self.tracks, "update_time": now, "version": 360000,
        }


def _image_size(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as im:
        return im.size


def _overlay_transform(iw: int, ih: int, c: dict[str, Any], width: int, height: int) -> tuple[float, float, float]:
    """ffmpeg 기준 위치(중심 x·y 비율, 폭 비율)를 CapCut clip 값(x, y, scale)으로 바꾼다.

    CapCut 은 scale 1 일 때 사진을 화면 안에 꽉 차게(비율 유지) 맞추므로, 그 크기 대비 배율을 구한다.
    """
    fit = min(width / iw, height / ih)
    scale = (width * float(c.get("width", 0.8))) / (iw * fit)
    x = (float(c.get("x", 0.5)) - 0.5) * 2
    y = (0.5 - float(c.get("y", 0.42))) * 2
    return x, y, round(scale, 5)


# ---------- 1. CapCut 프로젝트 ----------

async def build_draft(tl: dict[str, Any], job_dir: Path, draft_dir: Path, name: str,
                      font_path: str = "") -> dict[str, Any]:
    """draft_dir(아직 없는 새 폴더)에 재료를 복사하고 드래프트 JSON 을 쓴다. 반환: draft_content dict"""
    width, height, fps = int(tl["width"]), int(tl["height"]), int(tl["fps"])
    res = draft_dir / "Resources"
    res.mkdir(parents=True)
    copied: dict[Path, Path] = {}

    def bring(src: Path, name_hint: str = "") -> Path:
        src = Path(src)
        if src in copied:
            return copied[src]
        dst = res / (name_hint or src.name)
        n = 2
        while dst.exists():
            dst = res / f"{dst.stem}_{n}{dst.suffix}"
            n += 1
        shutil.copy2(src, dst)
        copied[src] = dst
        return dst

    d = _Draft(width, height, fps)
    total = total_duration(tl)

    # 장면 (메인 영상 트랙)
    scene_segs = []
    for s in tl["scenes"]:
        v = s["visual"]
        src = resolve(v["path"], job_dir)
        if v["kind"] == "video":
            path = await asyncio.to_thread(bring, src)
            info = await probe_video(path)
            st = (info.get("streams") or [{}])[0]
            dur = float((info.get("format") or {}).get("duration") or 0) or s["duration"]
            mid = d.media(path, "video", _us(dur), int(st.get("width") or width), int(st.get("height") or height),
                          bool(v.get("has_audio")))
            scene_segs.append(d.segment(mid, s["start"], s["duration"], src_start=v.get("src_start", 0.0),
                                        volume=float(tl["source_volume"]) if v.get("has_audio") else 0.0,
                                        canvas=True))
        else:
            path = await asyncio.to_thread(bring, src, f"scene_{s['index'] + 1:02d}{src.suffix}")
            iw, ih = await asyncio.to_thread(_image_size, path)
            mid = d.media(path, "photo", PHOTO_DURATION, iw, ih, False)
            scene_segs.append(d.segment(mid, s["start"], s["duration"], canvas=True))
    d.track("video", scene_segs)

    # 댓글 캡처 (두 번째 영상 트랙, 화면 속 화면)
    ov_segs = []
    for c in tl.get("comments", []):
        if c["kind"] != "image":
            continue
        src = resolve(c["path"], job_dir)
        if not src.is_file():
            continue
        path = await asyncio.to_thread(bring, src)
        iw, ih = await asyncio.to_thread(_image_size, path)
        x, y, scale = _overlay_transform(iw, ih, c, width, height)
        mid = d.media(path, "photo", PHOTO_DURATION, iw, ih, False)
        ov_segs.append(d.segment(mid, c["start"], c["end"] - c["start"], x=x, y=y, scale=scale))
    d.track("video", ov_segs)

    # 나레이션
    narr = await asyncio.to_thread(bring, resolve(tl["narration"], job_dir), "narration.mp3")
    narr_dur = await probe_duration(narr)
    nid = d.audio(narr, _us(narr_dur))
    d.track("audio", [d.segment(nid, 0, min(narr_dur, total), visual=False)])

    # 배경음악 - 영상보다 짧으면 이어 붙인다
    if tl.get("bgm"):
        bgm_src = resolve(tl["bgm"], job_dir)
        if bgm_src.is_file():
            bgm = await asyncio.to_thread(bring, bgm_src, "bgm" + bgm_src.suffix)
            bgm_dur = await probe_duration(bgm)
            bid = d.audio(bgm, _us(bgm_dur))
            segs, t = [], 0.0
            while t < total - 0.05 and bgm_dur > 0.5:
                seg_len = min(bgm_dur, total - t)
                segs.append(d.segment(bid, t, seg_len, volume=float(tl["bgm_volume"]), visual=False))
                t += seg_len
            d.track("audio", segs)

    style = tl["subtitles"]["style"]
    # 하단 자막 (자막을 끈 영상이면 트랙 자체가 없다)
    if tl["subtitles"].get("enabled", True):
        segs = []
        for ln in tl["subtitles"]["lines"]:
            mid = d.text(ln["text"], size=13, color=style.get("highlight", "#FFD400"),
                         stroke=style.get("outline", "#000000"), font_path=font_path, kind="subtitle")
            segs.append(d.segment(mid, ln["start"], ln["end"] - ln["start"], y=-0.42, text=True))
        d.track("text", segs)
    # 상단 키워드
    if tl["subtitles"].get("titles_enabled", True):
        segs = []
        for s in tl["scenes"]:
            if s.get("title", "").strip():
                mid = d.text(s["title"].strip(), size=15, stroke=style.get("outline", "#000000"),
                             font_path=font_path)
                segs.append(d.segment(mid, s["start"], s["duration"], y=0.7, text=True))
        d.track("text", segs)
    # 출처 표기 + 유튜브 댓글 글자 카드
    segs = []
    for s in tl["scenes"]:
        if s.get("credit"):
            mid = d.text(s["credit"], size=5, color="#DDDDDD", stroke="", font_path=font_path)
            segs.append(d.segment(mid, s["start"], s["duration"], y=-0.9, text=True))
    for c in tl.get("comments", []):
        if c["kind"] == "text":
            mid = d.text(f"💬 유튜브 댓글\n{c['text']}", size=8, stroke="", font_path=font_path,
                         background="#202634")
            segs.append(d.segment(mid, c["start"], c["end"] - c["start"],
                                  x=(float(c.get("x", 0.5)) - 0.5) * 2, y=(0.5 - float(c.get("y", 0.42))) * 2,
                                  text=True))
    d.track("text", segs)

    content = d.content(name, _us(total))
    body = json.dumps(content, ensure_ascii=False)
    (draft_dir / "draft_content.json").write_text(body, encoding="utf-8")
    (draft_dir / "draft_info.json").write_text(body, encoding="utf-8")
    now_us = int(time.time() * US)
    meta = {
        "draft_cover": "", "draft_fold_path": draft_dir.as_posix(), "draft_id": _uid(),
        "draft_is_ai_shorts": False, "draft_is_invisible": False,
        "draft_materials": [{"type": t, "value": []} for t in (0, 1, 2, 3, 6, 7, 8)],
        "draft_materials_copied_info": [], "draft_name": draft_dir.name, "draft_new_version": "",
        "draft_removable_storage_device": "", "draft_root_path": draft_dir.parent.as_posix(),
        "draft_segment_extra_info": [], "draft_timeline_materials_size_": 0, "draft_type": "",
        "tm_draft_cloud_completed": "", "tm_draft_cloud_modified": 0, "tm_draft_create": now_us,
        "tm_draft_modified": now_us, "tm_draft_removed": 0, "tm_duration": _us(total),
    }
    (draft_dir / "draft_meta_info.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return content


def default_font_path() -> str:
    for name in ("malgunbd.ttf", "malgun.ttf"):
        p = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / name
        if p.is_file():
            return str(p)
    return ""


async def export_draft(tl: dict[str, Any], job_dir: Path, root: Path, name: str) -> Path:
    """CapCut 드래프트 폴더에 새 프로젝트를 만든다. 실패하면 만들다 만 폴더를 지운다."""
    if not root or not Path(root).is_dir():
        raise RuntimeError("CapCut 프로젝트 폴더를 찾지 못했습니다. CapCut 을 한 번 실행해 주세요.")
    draft_dir = _unique_dir(Path(root), safe_name(name))
    try:
        await build_draft(tl, job_dir, draft_dir, draft_dir.name, default_font_path())
    except Exception:
        shutil.rmtree(draft_dir, ignore_errors=True)
        raise
    return draft_dir


# ---------- 2. 재료 묶음 ----------

def _clock(sec: float) -> str:
    return f"{int(sec // 60):02d}:{sec % 60:05.2f}"


async def export_pack(tl: dict[str, Any], job_dir: Path, out_zip: Path) -> Path:
    """장면 파일·음성·SRT·댓글 캡처·순서표를 zip 하나로 묶는다. CapCut 에서 순서대로 끌어다 쓰면 된다."""
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        order = ["[장면 순서] 번호 / 시작 / 길이 / 파일 / 상단 키워드"]
        for s in tl["scenes"]:
            v = s["visual"]
            src = resolve(v["path"], job_dir)
            n = f"{s['index'] + 1:02d}"
            if v["kind"] == "video":   # 쓴 구간만 잘라 둔다
                dst = tmp / f"{n}_장면.mp4"
                await run_ffmpeg(["-ss", f"{float(v.get('src_start', 0)):.3f}", "-i", str(src),
                                  "-t", f"{float(s['duration']):.3f}", "-c:v", "libx264", "-preset", "veryfast",
                                  "-crf", "20", "-c:a", "aac", "-b:a", "160k", str(dst)])
            else:
                dst = tmp / f"{n}_장면{src.suffix}"
                await asyncio.to_thread(shutil.copy2, src, dst)
            order.append(f"{n} / {_clock(s['start'])} / {s['duration']:.2f}초 / {dst.name} / {s.get('title', '')}")

        await asyncio.to_thread(shutil.copy2, resolve(tl["narration"], job_dir), tmp / "narration.mp3")
        order += ["", "narration.mp3 - 나레이션 (0초부터)"]
        if tl.get("bgm") and resolve(tl["bgm"], job_dir).is_file():
            bgm = resolve(tl["bgm"], job_dir)
            await asyncio.to_thread(shutil.copy2, bgm, tmp / f"bgm{bgm.suffix}")
            order.append(f"bgm{bgm.suffix} - 배경음악 (볼륨 약 {float(tl['bgm_volume']) * 100:.0f}%)")

        if tl["subtitles"].get("enabled", True) and tl["subtitles"]["lines"]:
            write_srt(tl["subtitles"]["lines"], tmp / "subtitles.srt")
            order.append("subtitles.srt - 하단 자막 (CapCut: 텍스트 → 자막 가져오기)")
        if tl["subtitles"].get("titles_enabled", True):
            titles = [{"start": s["start"], "end": s["start"] + s["duration"], "text": s["title"]}
                      for s in tl["scenes"] if s.get("title", "").strip()]
            if titles:
                write_srt(titles, tmp / "keywords.srt")
                order.append("keywords.srt - 상단 키워드")

        comments = tl.get("comments", [])
        if comments:
            (tmp / "comments").mkdir()
            order += ["", "[댓글] 시작 / 끝 / 내용"]
            for k, c in enumerate(comments, 1):
                if c["kind"] == "image":
                    src = resolve(c["path"], job_dir)
                    if src.is_file():
                        dst = tmp / "comments" / f"{k:02d}_{src.name}"
                        await asyncio.to_thread(shutil.copy2, src, dst)
                        order.append(f"{_clock(c['start'])} / {_clock(c['end'])} / 캡처 comments/{dst.name}")
                else:
                    order.append(f"{_clock(c['start'])} / {_clock(c['end'])} / {c['text']}")
        (tmp / "순서.txt").write_text("\n".join(order) + "\n", encoding="utf-8")

        def _zip() -> None:
            part = out_zip.with_suffix(".zip.part")
            with zipfile.ZipFile(part, "w") as z:
                for p in sorted(tmp.rglob("*")):
                    if p.is_file():
                        stored = p.suffix.lower() in (".mp4", ".mp3", ".jpg", ".jpeg", ".png", ".webp")
                        z.write(p, p.relative_to(tmp).as_posix(),
                                compress_type=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED)
            part.replace(out_zip)

        await asyncio.to_thread(_zip)
    return out_zip
