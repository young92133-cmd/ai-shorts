"""Adaptive presentation of existing timeline material; no content generation.

Optional blueprint/script hints are accepted only when they still identify the
same scene. Missing/stale hints keep the original raster intact. Rights-checked
parents can unwrap an already composited image without fetching new material.
"""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from .sources import SourceRegistry


def safe_area(options: dict) -> dict:
    from .hyperframes import AdapterValidationError, number
    raw = options.get("safe_area", {})
    if not isinstance(raw, dict):
        raise AdapterValidationError("safe_area must be an object")
    result = {k: int(number(raw.get(k, v), "safe_area." + k, maximum=1920))
              for k, v in dict(left=72, right=150, top=250, bottom=400).items()}
    result.update(width=1080-result["left"]-result["right"], height=1920-result["top"]-result["bottom"])
    if result["width"] < 600 or result["height"] < 1100:
        raise AdapterValidationError("Safe area leaves too little room for readable content")
    return result


@lru_cache(maxsize=96)
def font(size: int):
    from .hyperframes import FONT
    result = ImageFont.truetype(str(FONT), size)
    result.set_variation_by_axes([700])
    return result


def text_rows(text: str, width: int, maximum: int = 104, max_rows: int = 2) -> tuple[list[str], int]:
    """Fit whole words without ellipsis or breaking Korean words."""
    from .hyperframes import AdapterValidationError
    for size in range(maximum, 15, -2):
        rows, current = [], ""
        for word in text.split():
            trial = (current + " " + word).strip()
            if font(size).getlength(trial) <= width:
                current = trial
            else:
                if current:
                    rows.append(current)
                current = word
        if current:
            rows.append(current)
        if len(rows) <= max_rows and all(font(size).getlength(row) <= width for row in rows):
            return rows, size
    raise AdapterValidationError("Important text cannot fit without truncation")


def _sidecar(job: Path, name: str, default):
    from .hyperframes import AdapterValidationError
    path = job / name
    if not path.exists():
        return default
    if not path.resolve().is_relative_to(job.resolve()) or path.stat().st_size > 4_000_000:
        raise AdapterValidationError("Invalid local scene metadata")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise AdapterValidationError("Unreadable local scene metadata") from exc


def presentations(data: dict, job: Path) -> list[dict]:
    from .hyperframes import IMAGE_EXT, _text, local_asset
    blueprint = _sidecar(job, "blueprint.json", {}).get("scenes", [])
    script = _sidecar(job, "script.json", {}).get("scenes", [])
    _sidecar(job, "sources.json", [])  # Size/symlink guard before the common rights reader.
    registry = SourceRegistry(job)
    plans = []
    for i, scene in enumerate(data["scenes"]):
        plan = {"kind": "media", "path": scene["path"], "evidence": "timeline"}
        item = registry.by_path(scene["path"])
        # Only the exact original parent of this timeline asset, with existing
        # rights, can replace a composited raster. No filename guesses/downloads.
        if scene["kind"] == "image" and item and item.parent_id:
            parent = registry.items.get(item.parent_id)
            if parent and parent.kind == "image" and parent.usable_in_video and parent.credit == scene["credit"]:
                plan.update(path=local_asset(parent.path, job, IMAGE_EXT), evidence="rights-checked parent:" + parent.id)
        if i < len(blueprint) and i < len(script):
            b, s = blueprint[i], script[i]
            decision = b.get("visual_decision") or {}
            same = (abs(float(b.get("start", -1))-scene["start"]) < .02
                    and abs(float(b.get("duration", -1))-scene["duration"]) < .02
                    and _text(b.get("emphasis_text")) == _text(s.get("on_screen_text"))
                    and _text(b.get("narration")) == _text(s.get("narration"))
                    and Path(str(decision.get("asset_path", "")).replace("\\", "/")).name == scene["path"].name)
            if same:
                # Transition timing is optional presentation metadata, never a
                # change to scene/voice clocks or the source timeline file.
                plan["fade"] = min(.22, scene["duration"]/4) if b.get("transition") == "fade" else scene["fade"]
                if (scene["kind"] == "image" and data["titles"] and item and item.origin == "generated"
                        and item.usable_in_video and str(decision.get("resolved_visual_type", "")).endswith("_card")):
                    title = _text(b.get("emphasis_text"))
                    if title:
                        plan.update(kind="native", title=title, evidence="matched blueprint/script; original generated card",
                                    compare=[_text(s.get("compare_a")), _text(s.get("compare_b"))], key_number=_text(s.get("key_number")))
                        # Only explicitly saved cardinal step counts; no heights
                        # or statistical values are inferred from prose.
                        match = re.search(r"\b([2-5])단(?:계|\s)", _text(s.get("visual_description")))
                        plan["steps"] = int(match[1]) if match else 0
                        plan["step_evidence"] = match[0] if match else ""
        plans.append(plan)
    return plans


def image_geometry(path: Path) -> dict:
    with Image.open(path) as im:
        w, h = ImageOps.exif_transpose(im).size
    retention = min((w/h)/(1080/1920), (1080/1920)/(w/h))
    # Never throw away more than a quarter of an unannotated subject. Wide or
    # small sources use a sharp intact foreground over an inexpensive blur.
    cover = retention >= .75 and w >= 720 and h >= 1000
    scale = min(828/w, 780/h, 2.5)
    return {"mode": "cover" if cover else "contain-blur", "source_size": [w, h],
            "retained_fraction_if_cover": retention, "foreground_size": [round(w*scale), round(h*scale)]}


def blurred_background(path: Path, target: Path) -> None:
    with Image.open(path) as im:
        image = ImageOps.fit(ImageOps.exif_transpose(im).convert("RGB"), (270, 480))
        image = ImageEnhance.Brightness(image.filter(ImageFilter.GaussianBlur(16))).enhance(.42)
        image.resize((1080, 1920), Image.Resampling.BILINEAR).save(target, quality=90)


def native_background(target: Path) -> None:
    # Reuse the Shorts graphic helper. Rasterize static decoration once rather
    # than repaint a full-screen CSS gradient and oversized circle 889 times.
    # Text, captions and meaningful motion remain separate live HTML layers.
    from .cards import _background
    image = _background(1080, 1920, (18, 52, 72), (11, 17, 32), 0)
    ImageDraw.Draw(image).ellipse((480,40,1580,1140),outline='#325563',width=2)
    image.save(target, quality=95, subsampling=0)


def css(safe: dict) -> str:
    x, y, w, bottom = safe["left"], safe["top"], safe["width"], 1920-safe["bottom"]
    return f"""
    .scene img.full-background,.scene-media.full-background {{left:0;top:0;width:1080px;height:1920px;object-fit:cover;}}
    .adaptive-scene {{background:#0b1120 url('assets/native-background.jpg') 0 0/1080px 1920px;}}
    .native-heading,.adaptive-title {{position:absolute;left:{x}px;width:{w}px;text-align:left;font-weight:800;line-height:1.18;z-index:30;}}
    .native-heading {{top:{y+300}px;}}
    .adaptive-title {{top:{y+48}px;}}
    .native-row {{display:block;white-space:nowrap;}}
    .accent-rule {{position:absolute;left:{x}px;top:{y+590}px;width:150px;height:8px;background:#65edba;transform-origin:left;}}
    .motif-arrow {{position:absolute;left:{x}px;top:{y+690}px;width:{w}px;height:5px;background:linear-gradient(90deg,#65edba,transparent);transform-origin:left;}}
    .motif-arrow::after {{content:'';position:absolute;right:20px;top:-15px;width:30px;height:30px;border-top:5px solid #65edba;border-right:5px solid #65edba;transform:rotate(45deg);}}
    .compare-panel {{position:absolute;left:{x}px;width:{w}px;padding:24px 30px;border-left:7px solid #65edba;background:#17303c;line-height:1.25;font-weight:700;}}
    .native-number {{position:absolute;left:{x}px;top:{y+630}px;width:{w}px;line-height:1.2;font-weight:800;color:#65edba;}}
    .step {{position:absolute;background:#25746c;border-top:7px solid #65edba;transform-origin:bottom;}}
    .step-fill {{position:absolute;inset:0;background:#25746c;border-top:7px solid #65edba;transform-origin:bottom;}}
    .step-label {{position:absolute;inset:20px 0 auto;text-align:center;font-size:44px;font-weight:800;}}
    .step-note {{position:absolute;left:{x}px;top:{y+850}px;width:{w}px;text-align:left;font-size:28px;color:#b6ccc9;}}
    .caption {{left:{x}px;top:{bottom-178}px;width:{w}px;padding:12px 16px;background:rgba(7,17,29,.88);border-radius:16px;line-height:1.3;}}
    .credit {{left:{x}px;top:{bottom-280}px;width:{w}px;text-align:left;color:#e2eceb;text-shadow:0 2px 4px #000;}}
    .scene img.media-foreground {{object-fit:contain;}}
    .scene.video-overlay {{background:transparent;z-index:2!important;}}
    .scene.video-overlay::before {{display:none;}}
    .video-background {{position:absolute;inset:0;width:1080px;height:1920px;object-fit:cover;z-index:1;}}
    .scene-media.adaptive-video {{left:0;top:450px;width:1080px;height:1000px;object-fit:contain;z-index:1;}}
    .overlay {{left:{x}px;top:{y+690}px;width:{w}px;}}
    """


def scene_layers(i: int, scene: dict, plan: dict, data: dict, safe: dict, copy, project: Path) -> tuple:
    from .hyperframes import _esc, _font_size
    start, dur = scene["start"], scene["duration"]
    fade = plan.get("fade", scene["fade"]) if i else 0
    # A crossfade extends only the previous visual, never the voice or captions.
    end_extension = data["scenes"][i+1].get("adaptive_fade", 0) if i+1 < len(data["scenes"]) else 0
    clock = f'data-start="{start:.6f}" data-duration="{dur+end_extension:.6f}" data-track-index="{i}"'
    content, tweens, videos = [], [], []
    record = {"index": i, "kind": plan["kind"], "evidence": plan["evidence"], "start": start, "duration": dur}
    width = safe["width"]
    def text(ident, value, cls, maximum, top=None):
        rows, size = text_rows(value, width-64, maximum)
        body = ''.join(f'<span class="native-row">{_esc(row)}</span>' for row in rows)
        top_css = f'top:{top}px;' if top is not None else ''
        content.append(f'<div id="{ident}" class="{cls}" data-key-text="true" style="font-size:{size}px;{top_css}">{body}</div>')
        return size
    if plan["kind"] == "native":
        title = plan["title"]
        record.update(title=title, title_size=text(f"native-title-{i}", title, "native-heading", 104))
        content.append(f'<div id="rule-{i}" class="accent-rule"></div>')
        tweens += [f'tl.fromTo("#native-title-{i}",{{y:32,opacity:0}},{{y:0,opacity:1,duration:0.32,ease:"power2.out"}},{start:.6f});',
                   f'tl.fromTo("#rule-{i}",{{scaleX:0}},{{scaleX:1,duration:0.5,ease:"power2.out"}},{start+.14:.6f});']
        if all(plan["compare"]):
            # Move the heading up so two semantic panels stay above captions.
            content[0] = content[0].replace('style="', f'style="top:{safe["top"]+90}px;')
            for j, value in enumerate(plan["compare"]):
                text(f"compare-{i}-{j}", value, "compare-panel", 58, safe["top"]+390+j*235)
                tweens.append(f'tl.fromTo("#compare-{i}-{j}",{{x:24,opacity:0}},{{x:0,opacity:1,duration:0.35}},{start+.18+j*.25:.6f});')
        elif plan.get("key_number"):
            text(f"number-{i}", plan["key_number"], "native-number", 132)
            record["key_number"] = plan["key_number"]
            tweens.append(f'tl.fromTo("#number-{i}",{{y:24,opacity:0}},{{y:0,opacity:1,duration:0.4,ease:"power2.out"}},{start+.2:.6f});')
        elif plan.get("steps"):
            count = plan["steps"]; bar_w = (width-24*(count-1))/count
            for j in range(count):
                h = 100+j*60
                content.append(f'<div class="step" style="background:none;border:0;left:{safe["left"]+j*(bar_w+24):.2f}px;top:{safe["top"]+800-h}px;width:{bar_w:.2f}px;height:{h}px"><div id="step-{i}-{j}" class="step-fill"></div>'
                               f'<span class="step-label" data-key-text="true">{j+1}</span></div>')
                tweens.append(f'tl.fromTo("#step-{i}-{j}",{{scaleY:0}},{{scaleY:1,duration:0.45,ease:"power2.out"}},{start+.25+j*.17:.6f});')
            content.append('<div class="step-note" data-key-text="true">구간 구조 · 높이는 요금 비율이 아님</div>')
            record.update(steps=count, step_evidence=plan["step_evidence"], quantitative_chart=False)
        else:
            content.append(f'<div id="arrow-{i}" class="motif-arrow"></div>')
            tweens.append(f'tl.fromTo("#arrow-{i}",{{scaleX:0}},{{scaleX:1,duration:0.65,ease:"power2.out"}},{start+.3:.6f});')
    else:
        source = copy(plan["path"])
        record["source"] = str(plan["path"])
        if scene["kind"] == "video":
            target = f"assets/scene-{i}.mp4"
            videos.append({**scene, "source":project/source, "target":project/target, "background":project/f"assets/video-background-{i}.jpg"})
            content.append(f'<video id="visual-{i}" class="clip scene-media adaptive-video" src="{target}" data-start="{start:.6f}" data-duration="{dur:.6f}" data-media-start="0" data-hf-media-start-basis="local" muted playsinline></video>')
            tweens.append(f'tl.fromTo("#visual-{i}",{{scale:1}},{{scale:1.012,duration:{dur:.6f},ease:"none"}},{start:.6f});')
            record["fit"] = "intact original-aspect video / static preblurred full-frame background"
        else:
            geometry = image_geometry(plan["path"]); record.update(geometry)
            if geometry["mode"] == "cover":
                content.append(f'<img id="visual-{i}" class="full-background" src="{source}" alt="" />')
            else:
                background = project/f"assets/background-{i}.jpg"; blurred_background(plan["path"], background)
                w,h = geometry["foreground_size"]
                content.append(f'<img class="full-background" src="assets/background-{i}.jpg" alt="" />')
                content.append(f'<img id="visual-{i}" class="media-foreground" src="{source}" alt="" style="left:{safe["left"]+(width-w)/2}px;top:{safe["top"]+240+(780-h)/2}px;width:{w}px;height:{h}px;" />')
            if scene["effect"] != "none":
                a,b = (1,1.018) if scene["effect"] == "zoom_in" else (1.018,1)
                tweens.append(f'tl.fromTo("#visual-{i}",{{scale:{a}}},{{scale:{b},duration:{dur:.6f},ease:"none"}},{start:.6f});')
        if scene["title"] and data["titles"]:
            record["title_size"] = text(f"title-{i}", scene["title"], "adaptive-title", 84)
    if scene["credit"]:
        size = _font_size([scene["credit"]], 28, width-40)
        content.append(f'<div id="credit-{i}" class="credit" data-key-text="true" style="font-size:{size}px">{_esc(scene["credit"])}</div>')
    # Timed video must be a direct stage child. A timed wrapper would apply a
    # second clock in the producer's media extractor (also rejected by lint).
    media = ""
    video_scene = scene["kind"] == "video" and plan["kind"] == "media"
    if video_scene:
        media = content.pop(0)
        media = (f'<img id="video-background-{i}" class="clip video-background" src="assets/video-background-{i}.jpg" alt="" '
                 f'data-start="{start:.6f}" data-duration="{dur+end_extension:.6f}" />') + media
        if fade:
            tweens.append(f'tl.fromTo("#visual-{i}",{{opacity:0}},{{opacity:1,duration:{fade:.6f},ease:"none"}},{start:.6f});')
    classes = "clip scene adaptive-scene" + (" video-overlay" if video_scene else "")
    markup = media + f'<div id="scene-{i}" class="{classes}" {clock} style="z-index:1">{"".join(content)}</div>'
    if fade:
        tweens.append(f'tl.fromTo("#scene-{i}",{{opacity:0}},{{opacity:1,duration:{fade:.6f},ease:"none"}},{start:.6f});')
    return markup, tweens, videos, record
