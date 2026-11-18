"""Local, optional HyperFrames adapter for the existing V1 timeline.

No LLM/TTS, npm install, remote assets or changes to the FFmpeg renderer.
The exported HTML is derived output; timeline.json remains the source of truth.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import hashlib
import html
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import signal
import subprocess
import threading
import time
from typing import Any

from .media import run_ffmpeg, has_audio, probe_duration, probe_video
from .models import Word
from .subtitles import group_lines

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / ".tools" / "hyperframes"
RENDERER = ROOT / "renderers" / "hyperframes"
FONT = RENDERER / "poc" / "assets" / "fonts" / "NotoSansKR-VF.ttf"
GSAP = RENDERER / "poc" / "assets" / "vendor" / "gsap.min.js"
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXT = {".mp4", ".webm", ".mov", ".mkv", ".m4v"}
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"}


class HyperframesError(RuntimeError):
    """Only local availability/execution failures may explicitly fall back."""


class AdapterValidationError(ValueError):
    """Invalid/untrusted input must never fall back to a less strict path."""


def number(value: Any, name: str, minimum: float = 0, maximum: float = 86400) -> float:
    if isinstance(value, bool):
        raise AdapterValidationError(f"{name}: expected a finite number")
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise AdapterValidationError(f"{name}: expected a finite number") from exc
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise AdapterValidationError(f"{name}: out of range")
    return result


def local_asset(value: Any, job_dir: Path, extensions: set[str],
                asset_roots: list[Path] | None = None) -> Path:
    """Allow only regular media inside the job or explicitly trusted local roots."""
    if not isinstance(value, (str, Path)) or not str(value):
        raise AdapterValidationError("Missing local media path")
    text = str(value)
    win = PureWindowsPath(text)
    if any(ord(c) < 32 for c in text) or text.startswith(("//", "\\\\")):
        raise AdapterValidationError("UNC/device/control-character paths are not allowed")
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", text) and not re.match(r"^[A-Za-z]:[\\/]", text):
        raise AdapterValidationError("URLs and drive-relative paths are not local media")
    if win.drive and (not win.is_absolute() or os.name != "nt"):
        raise AdapterValidationError("Unsupported Windows media path")
    p = Path(text.replace("\\", os.sep))
    if not p.is_absolute():
        p = job_dir / p
    try:
        resolved = p.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise AdapterValidationError(f"Missing/unreadable media: {p.name}") from exc
    roots = [job_dir.resolve(), *(p.resolve() for p in asset_roots or [])]
    if not any(resolved.is_relative_to(root) for root in roots):
        raise AdapterValidationError(f"Media is outside the trusted asset roots: {p.name}")
    if not resolved.is_file() or resolved.suffix.lower() not in extensions:
        raise AdapterValidationError(f"Unsupported media file: {p.name}")
    return resolved


def _text(value: Any) -> str:
    value = str(value or "")
    if len(value) > 2000 or "\x00" in value:
        raise AdapterValidationError("Screen text is too long or contains NUL")
    return " ".join(value.split())


def _esc(value: Any) -> str:
    return html.escape(_text(value), quote=True)


def _color(value: Any, default: str) -> str:
    return value if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) else default


def caption_pages(lines: list[dict], total: float) -> list[dict]:
    """Use original word times; wrap at word/sentence boundaries, never truncate."""
    pages = []
    previous_end = 0.0
    for line in lines:
        start = number(line.get("start"), "caption start", maximum=total)
        end = number(line.get("end"), "caption end", minimum=start + 0.001, maximum=total + 0.05)
        if start < previous_end - 0.01:
            raise AdapterValidationError("Overlapping caption lines")
        previous_end = end
        if not line.get("words"):
            text = _text(line.get("text"))
            tokens = text.split()
            # Untimed legacy captions remain static; no invented speech timings.
            words = [Word(text=t, start=start, end=end) for t in tokens]
            timed = False
        else:
            words, last = [], start
            for raw in line["words"]:
                a = number(raw.get("start"), "word start", minimum=start, maximum=end)
                b = number(raw.get("end"), "word end", minimum=a, maximum=end)
                text = _text(raw.get("text"))
                if not text.strip() or a < last - 0.01:
                    raise AdapterValidationError("Empty/overlapping caption word")
                words.append(Word(text=text, start=a, end=b)); last = b
            timed = True
        rows, sentence = [], []
        for word in words:
            sentence.append(word)
            if re.search(r"[.!?。！？]$", word.text):
                rows.extend(group_lines(sentence, max_chars=14, max_words=999, max_gap=0.8))
                sentence = []
        rows.extend(group_lines(sentence, max_chars=14, max_words=999, max_gap=0.8))
        if not timed and len(rows) > 2:
            # A static cue cannot be paged without inventing time. Fit two intact rows.
            split = max(1, len(words) // 2)
            rows = [words[:split], words[split:]]
        for i in range(0, len(rows), 2):
            group = rows[i:i+2]
            page_start = start if i == 0 else group[0][0].start
            page_end = rows[i+2][0].start if i+2 < len(rows) else end
            pages.append({"start": page_start, "end": page_end, "rows": [
                [{"text": w.text, "start": w.start, "end": w.end} for w in row] for row in group], "timed": timed})
    return pages


def validate(tl: dict, job_dir: Path, options: dict | None = None) -> dict:
    options = options or {}
    if tl.get("version", 1) != 1:
        raise AdapterValidationError("Unsupported timeline version")
    if (tl.get("width"), tl.get("height"), tl.get("fps")) != (1080, 1920, 30):
        raise AdapterValidationError("Initial HyperFrames integration supports 1080x1920 at 30 fps")
    roots = [ROOT / "assets", *(Path(p) for p in options.get("asset_roots", []))]
    scenes, time_end = [], 0.0
    if not isinstance(tl.get("scenes"), list) or not tl["scenes"]:
        raise AdapterValidationError("Timeline has no scenes")
    for i, scene in enumerate(tl["scenes"]):
        start = number(scene.get("start", time_end), "scene start")
        duration = number(scene.get("duration"), "scene duration", minimum=0.001)
        if abs(start - time_end) > 0.02:
            raise AdapterValidationError("Scene times must be contiguous and ordered")
        visual = scene.get("visual") or {}
        kind = visual.get("kind")
        if kind not in ("image", "video"):
            raise AdapterValidationError("Scene visual must be image/video")
        path = local_asset(visual.get("path"), job_dir, IMAGE_EXT if kind == "image" else VIDEO_EXT, roots)
        offset = number(visual.get("src_start", 0), "source start")
        play = number(visual.get("play", duration), "source play", minimum=0.001, maximum=duration)
        effect = scene.get("effect", "zoom_in" if i % 2 == 0 else "zoom_out")
        if effect not in ("none", "zoom_in", "zoom_out"):
            raise AdapterValidationError("Unsupported scene effect")
        transition = scene.get("transition", tl.get("transition", 0) if tl.get("mode") == "slideshow" else 0)
        fade = min(number(transition, "transition", maximum=5), duration / 2)
        scenes.append({"start": start, "duration": duration, "kind": kind, "path": path,
                       "src_start": offset, "play": play, "has_audio": bool(visual.get("has_audio")),
                       "title": _text(scene.get("title")), "credit": _text(scene.get("credit")),
                       "effect": effect, "fade": fade})
        time_end = start + duration
    audio = {}
    for field in ("narration", "bgm"):
        audio[field] = local_asset(tl[field], job_dir, AUDIO_EXT, roots) if tl.get(field) else None
    audio.update(bgm_volume=number(tl.get("bgm_volume", 0.1), "BGM volume", maximum=4),
                 source_volume=number(tl.get("source_volume", 0.12), "source volume", maximum=4))
    sfx = []
    for sound in tl.get("sfx", []):
        sfx.append({"path": local_asset(sound.get("path"), job_dir, AUDIO_EXT, roots),
                    "start": number(sound.get("start", 0), "sfx start", maximum=time_end),
                    "volume": number(sound.get("volume", 1), "sfx volume", maximum=4)})
    sub = tl.get("subtitles") or {}
    pages = caption_pages(sub.get("lines") or [], time_end) if sub.get("enabled", True) else []
    return {"scenes": scenes, "total": time_end, "audio": audio, "sfx": sfx, "pages": pages,
            "titles": sub.get("titles_enabled", True),
            "highlight": _color((sub.get("style") or {}).get("highlight"), "#FFD400")}


def _font_size(rows: list[str], maximum: int = 52, width: int = 760) -> int:
    from .hyperframes_layout import font as noto_font
    font = noto_font(maximum)
    length = max((font.getlength(s) for s in rows), default=1)
    size = min(maximum, math.floor(maximum * width / max(1, length)))
    if size < 16:
        raise AdapterValidationError("Text cannot fit safely without becoming unreadable")
    return size


def export_project(tl: dict, job_dir: Path, project: Path, options: dict | None = None) -> dict:
    """Export escaped local HTML and original-timed captions, without external commands."""
    data = validate(tl, job_dir, options)
    options = options or {}
    layout = options.get("layout", "legacy")
    if layout not in ("legacy", "adaptive"):
        raise AdapterValidationError("HyperFrames layout must be legacy/adaptive")
    adaptive = layout == "adaptive"
    from . import hyperframes_layout as presentation
    safe = presentation.safe_area(options) if adaptive else None
    plans = presentation.presentations(data, job_dir) if adaptive else []
    for scene, plan in zip(data["scenes"], plans):
        scene["adaptive_fade"] = plan.get("fade", scene["fade"])
    if not FONT.is_file() or not GSAP.is_file():
        raise HyperframesError("Missing local Noto Sans KR/GSAP assets; restore the pinned renderer environment")
    project.mkdir(parents=True, exist_ok=False)
    assets = project / "assets"; assets.mkdir()
    if adaptive:
        presentation.native_background(assets / "native-background.jpg")
    shutil.copyfile(FONT, assets / "NotoSansKR-VF.ttf")
    shutil.copyfile(FONT.parent / "OFL.txt", assets / "OFL.txt")
    shutil.copyfile(GSAP, assets / "gsap.min.js")
    copied, manifest = {}, []
    def copy(path: Path) -> str:
        if path not in copied:
            with path.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            target = "assets/" + digest[:20] + path.suffix.lower()
            if not (project / target).exists():
                shutil.copyfile(path, project / target)
            copied[path] = target
            manifest.append({"original": str(path), "asset": target, "sha256": digest})
        return copied[path]
    markup, tweens, videos, layout_records = [], [], [], []
    total = data["total"]
    for i, scene in enumerate(data["scenes"]):
        if adaptive:
            layer, animations, prepared, record = presentation.scene_layers(i, scene, plans[i], data, safe, copy, project)
            markup.append(layer); tweens.extend(animations); videos.extend(prepared); layout_records.append(record)
            continue
        start, dur = scene["start"], scene["duration"]
        fade = scene["fade"] if i else 0
        duration = dur + (min(data["scenes"][i+1]["fade"], dur/2) if i+1 < len(data["scenes"]) else 0)
        source = copy(scene["path"])
        if scene["kind"] == "video":
            target = f"assets/scene-{i}.mp4"
            videos.append({**scene, "source": project / source, "target": project / target})
            # Only the actual media tag is timed. The engine owns every media seek.
            markup.append(f'<video id="scene-{i}" class="clip scene-media" src="{target}" '
                          f'data-start="{start:.6f}" data-duration="{dur:.6f}" data-track-index="{i}" '
                          'data-media-start="0" data-hf-media-start-basis="local" muted playsinline></video>')
        else:
            markup.append(f'<div id="scene-{i}" class="clip scene" data-start="{start:.6f}" '
                          f'data-duration="{duration:.6f}" data-track-index="{i}" style="z-index:{i+1}">'
                          f'<img id="visual-{i}" src="{source}" alt="" /></div>')
            if scene["effect"] != "none":
                a, b = (1, 1.025) if scene["effect"] == "zoom_in" else (1.025, 1)
                tweens.append(f'tl.fromTo("#visual-{i}",{{scale:{a}}},{{scale:{b},duration:{dur:.6f},ease:"none"}},{start:.6f});')
        if fade:
            tweens.append(f'tl.fromTo("#scene-{i}",{{opacity:0}},{{opacity:1,duration:{fade:.6f},ease:"none"}},{start:.6f});')
        if scene["title"] and data["titles"]:
            size = _font_size([scene["title"]], 38)
            markup.append(f'<div id="title-{i}" class="clip scene-title" data-key-text="true" data-start="{start:.6f}" '
                          f'data-duration="{dur:.6f}" style="font-size:{size}px">{_esc(scene["title"])}</div>')
        if scene["credit"]:
            size = _font_size([scene["credit"]], 28)
            markup.append(f'<div id="credit-{i}" class="clip credit" data-key-text="true" data-start="{start:.6f}" '
                          f'data-duration="{dur:.6f}" style="font-size:{size}px">{_esc(scene["credit"])}</div>')
    for i, page in enumerate(data["pages"]):
        texts = [" ".join(w["text"] for w in row) for row in page["rows"]]
        size = _font_size(texts, 58, safe["width"]-48) if adaptive else _font_size(texts)
        rows = []
        for r, row in enumerate(page["rows"]):
            spans = []
            for j, word in enumerate(row):
                ident = f"word-{i}-{r}-{j}"
                spans.append(f'<span id="{ident}">{_esc(word["text"])}</span>')
                if page["timed"]:
                    tweens.append(f'tl.set("#{ident}",{{color:"{data["highlight"]}"}},{word["start"]:.6f});')
                    tweens.append(f'tl.set("#{ident}",{{color:"#FFFFFF"}},{word["end"]:.6f});')
            rows.append('<span class="caption-row">' + ' '.join(spans) + '</span>')
        markup.append(f'<div id="caption-{i}" class="clip caption" data-key-text="true" data-start="{page["start"]:.6f}" '
                      f'data-duration="{page["end"]-page["start"]:.6f}" data-track-kind="captions" '
                      f'style="font-size:{size}px">{"".join(rows)}</div>')
        if adaptive:
            tweens.append(f'tl.fromTo("#caption-{i}",{{y:8}},{{y:0,duration:0.12,ease:"power2.out"}},{page["start"]:.6f});')
    comments = []
    roots = [ROOT / "assets", *(Path(p) for p in (options or {}).get("asset_roots", []))]
    for i, c in enumerate(tl.get("comments", [])):
        start = number(c.get("start"), "comment start", maximum=total)
        end = number(c.get("end"), "comment end", minimum=start+0.001, maximum=total)
        if c.get("kind") == "image":
            src = copy(local_asset(c.get("path"), job_dir, IMAGE_EXT, roots))
            content = f'<img src="{src}" alt="" />'
        elif c.get("kind") == "text":
            content = _esc(c.get("text"))
        else:
            raise AdapterValidationError("Unsupported overlay kind")
        comments.append(f'<div id="overlay-{i}" class="clip overlay" data-start="{start}" data-duration="{end-start}">{content}</div>')
    audio = {k: (project / copy(v) if isinstance(v, Path) else v) for k,v in data["audio"].items()}
    sfx = [{**s, "path": project / copy(s["path"])} for s in data["sfx"]]
    markup.extend(comments)
    template = (RENDERER / "scene.html").read_text(encoding="utf-8")
    # Insert untrusted (escaped) text last so it cannot become a template marker.
    page = template.replace("{{ADAPTIVE_CSS}}", presentation.css(safe) if adaptive else "").replace("{{DURATION}}", f"{total:.6f}").replace("{{TWEENS}}", "\n".join(tweens)).replace("{{MARKUP}}", "\n".join(markup))
    (project / "compositions").mkdir()
    (project / "compositions/shorts.html").write_text(page, encoding="utf-8")
    main = (RENDERER / "timeline.html").read_text(encoding="utf-8").replace("{{DURATION}}", f"{total:.6f}")
    (project / "index.html").write_text(main, encoding="utf-8")
    (project / "hyperframes.json").write_text(json.dumps({"media":{"autoProxy":True}}), encoding="utf-8")
    (project / "timeline-input.json").write_text(json.dumps(tl, ensure_ascii=False, indent=2), encoding="utf-8")
    (project / "asset-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (project / "caption-map.json").write_text(json.dumps(data["pages"], ensure_ascii=False, indent=2), encoding="utf-8")
    if adaptive:
        (project / "layout-map.json").write_text(json.dumps({"safe_area": safe, "scenes":layout_records}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"project": project, "total": total, "videos": videos, "audio": audio, "sfx": sfx,
            "adaptive": adaptive, "cache_media": options.get("cache_media", False) is True}


async def prepare_media(export: dict, duck_bgm: bool = False) -> None:
    project, total = export["project"], export["total"]
    prepared = []
    async def background(video):
        if video.get("background"):
            await run_ffmpeg(["-i",str(video["target"]),"-frames:v","1","-vf",
                              "scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=12:2,eq=brightness=-0.12,scale=1080:1920",
                              str(video["background"])],cwd=project)
    for v in export["videos"]:
        # The cache is content-addressed and only publishes complete local
        # derivatives. Original assets and the timeline remain untouched.
        with v["source"].open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        key = hashlib.sha256(json.dumps([digest,v["src_start"],v["play"],v["duration"],v.get("portrait",False),"hf-media-v2-ffmpeg9.0.1-crf18-gop30"],sort_keys=True).encode()).hexdigest()
        cache = TOOLS / "cache/prepared/v1" / (key + ".mp4")
        if export.get("cache_media") and cache.is_file() and cache.stat().st_size:
            shutil.copyfile(cache, v["target"])
            prepared.append({"target":v["target"].name,"cache_hit":True,"cache_key":key})
            await background(v)
            continue
        available = await probe_duration(v["source"]) - v["src_start"]
        if available <= 0:
            raise AdapterValidationError("Video source start is past EOF")
        play = min(v["play"], available)
        filters = f"trim=duration={play:.6f},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={v['duration']:.6f},trim=duration={v['duration']:.6f},fps=30,setsar=1"
        await run_ffmpeg(["-ss", f'{v["src_start"]:.6f}', "-i", str(v["source"]),
                          "-an", "-vf", filters,
                          "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-g", "30", "-keyint_min", "30", "-pix_fmt", "yuv420p", str(v["target"])], cwd=project)
        prepared.append({"target":v["target"].name,"cache_hit":False,"cache_key":key})
        if export.get("cache_media"):
            cache.parent.mkdir(parents=True, exist_ok=True)
            # render_slot serializes these writers; a crash leaves only .tmp.
            temporary = cache.with_suffix(".tmp")
            shutil.copyfile(v["target"], temporary); temporary.replace(cache)
        await background(v)
    audio = export["audio"]
    if (export.get("adaptive") and audio["narration"] and not audio["bgm"] and not export["sfx"]
            and not any(v["has_audio"] for v in export["videos"])):
        # HyperFrames already decodes/mixes the original file. Avoid an extra
        # MP3 -> WAV round trip when no actual mixing is needed.
        root = project / "index.html"
        relative = audio["narration"].relative_to(project).as_posix()
        root.write_text(root.read_text(encoding="utf-8").replace('src="assets/mix.wav"', f'src="{relative}"'), encoding="utf-8")
        (project / "media-preparation.json").write_text(json.dumps({"narration_passthrough":True,"videos":prepared}),encoding="utf-8")
        return
    args, filters = [], []
    idx = 0
    if audio["narration"]:
        args += ["-i", str(audio["narration"])]
    else:
        args += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    filters.append(f"[0:a]aformat=sample_rates=44100:channel_layouts=stereo,apad,atrim=duration={total:.6f},asetpts=PTS-STARTPTS[narr]")
    labels = ["[narr]"]
    idx += 1
    if audio["bgm"]:
        args += ["-stream_loop", "-1", "-i", str(audio["bgm"])]
        filters.append(f"[{idx}:a]aformat=sample_rates=44100:channel_layouts=stereo,atrim=duration={total:.6f},asetpts=PTS-STARTPTS,volume={audio['bgm_volume']}[bed]")
        idx += 1
        if duck_bgm and audio["narration"]:
            filters += ["[narr]asplit=2[voice][side]", "[bed][side]sidechaincompress=threshold=0.035:ratio=6:attack=20:release=250[ducked]"]
            labels = ["[voice]", "[ducked]"]
        else:
            labels.append("[bed]")
    sounds = list(export["sfx"])
    for v in export["videos"]:
        if v["has_audio"] and await has_audio(v["source"]):
            sounds.append({"path":v["source"], "start":v["start"], "src_start":v["src_start"],
                           "play":v["play"], "volume":audio["source_volume"]})
    for i, sound in enumerate(sounds):
        args += ["-i", str(sound["path"])]
        offset, play = sound.get("src_start", 0), sound.get("play", total)
        filters.append(f"[{idx}:a]atrim=start={offset}:duration={play},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo,volume={sound['volume']},adelay={round(sound['start']*1000)}:all=1[fx{i}]")
        labels.append(f"[fx{i}]"); idx += 1
    filters.append("".join(labels) + f"amix=inputs={len(labels)}:duration=first:normalize=0,apad,atrim=duration={total:.6f}[out]")
    await run_ffmpeg([*args, "-filter_complex", ";".join(filters), "-map", "[out]", "-c:a", "pcm_s16le", str(project / "assets/mix.wav")], cwd=project)
    (project / "media-preparation.json").write_text(json.dumps({"narration_passthrough":False,"videos":prepared}),encoding="utf-8")


@contextmanager
def render_slot(tool_root: Path = TOOLS):
    """One HyperFrames render across threads/processes; OS releases locks after crashes."""
    tool_root.mkdir(parents=True, exist_ok=True)
    with (tool_root / "render.lock").open("a+b") as f:
        f.seek(0, 2)
        if f.tell() == 0:
            f.write(b"0"); f.flush()
        f.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise HyperframesError("Another HyperFrames render is running; retry later") from exc
        try:
            yield
        finally:
            f.seek(0)
            if os.name == "nt":
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _execute(command: list[str], cwd: Path, env: dict, log: Path, timeout: float,
             cancelled: threading.Event | None = None) -> None:
    with log.open("w", encoding="utf-8") as output:
        proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
                                start_new_session=os.name != "nt")
        try:
            deadline = time.monotonic() + timeout
            while True:
                if cancelled is not None and cancelled.is_set():
                    raise HyperframesError("Render was cancelled")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                try:
                    code = proc.wait(timeout=min(0.2, remaining))
                    break
                except subprocess.TimeoutExpired:
                    pass
        except BaseException:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            raise HyperframesError(f"HyperFrames command interrupted/timed out; see {log}")
    if code:
        raise HyperframesError(f"HyperFrames exited {code}; see {log}")


async def _execute_async(command: list[str], cwd: Path, env: dict, log: Path, timeout: float) -> None:
    cancelled = threading.Event()
    task = asyncio.create_task(asyncio.to_thread(_execute, command, cwd, env, log, timeout, cancelled))
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        cancelled.set()
        try:
            await task
        except HyperframesError:
            pass
        raise


async def render_hyperframes(tl: dict, job_dir: Path, out: Path, project: Path, options: dict | None = None) -> Path:
    options = options or {}
    validate(tl, job_dir, options)  # Security/data errors are not eligible for fallback.
    workers = render_workers(options)
    node = TOOLS / "node.exe" if os.name == "nt" else TOOLS / "node"
    cli = RENDERER / "node_modules/hyperframes/bin/hyperframes.mjs"
    package = cli.parent.parent / "package.json"
    if not node.is_file() or not cli.is_file() or not package.is_file():
        raise HyperframesError("Pinned local Node/HyperFrames is missing; no automatic install was attempted")
    if json.loads(package.read_text(encoding="utf-8"))["version"] != "0.9.23":
        raise HyperframesError("HyperFrames must match the pinned 0.9.23 environment")
    browsers = list((TOOLS / "cache/chrome").rglob("chrome-headless-shell.exe" if os.name == "nt" else "chrome-headless-shell"))
    if not browsers:
        raise HyperframesError("Dedicated headless browser cache is missing; no automatic download was attempted")
    timeout = number(options.get("timeout_seconds", 600), "render timeout", minimum=10, maximum=3600)
    with render_slot():
        export = export_project(tl, job_dir, project, options)
        (project / 'runtime-settings.json').write_text(json.dumps({
            'requested_workers':options.get('workers',1), 'passed_workers':workers,
            'quality':'delivery', 'encoder':'software', 'fps':30,
            'note':'Actual worker/capture resolution is recorded by the HyperFrames CLI trace.'}),encoding='utf-8')
        try:
            await prepare_media(export, duck_bgm=options.get("duck_bgm") is True)
        except AdapterValidationError:
            raise
        except Exception as exc:
            (project / "media-error.log").write_text(str(exc), encoding="utf-8")
            raise HyperframesError(f"HyperFrames media preparation failed; see {project / 'media-error.log'}") from exc
        env = os.environ.copy()
        for name in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "HEYGEN_API_KEY", "GEMINI_API_KEY"]:
            env.pop(name, None)
        temp = TOOLS / "tmp"; temp.mkdir(parents=True, exist_ok=True)
        env.update({"PATH": str(TOOLS)+os.pathsep+env.get("PATH", ""), "TEMP":str(temp), "TMP":str(temp),
                    "HYPERFRAMES_CACHE_DIR":str(TOOLS / "cache"), "HYPERFRAMES_CONFIG_DIR":str(TOOLS / "config"),
                    "HYPERFRAMES_BROWSER_PATH":str(browsers[0]), "HYPERFRAMES_EXTRACT_CACHE_DIR":str(TOOLS / "cache/extracted"),
                    "HYPERFRAMES_SKIP_SKILLS":"1", "HYPERFRAMES_NO_TELEMETRY":"1", "DO_NOT_TRACK":"1"})
        await _execute_async([str(node), str(cli), "lint", str(project), "--json"],
                             project, env, project / "lint.log", min(timeout, 60))
        profile = ["--low-memory-mode"] if options.get("low_memory") is True else []
        await _execute_async([str(node), str(cli), "render", str(project), "--fps", "30", "--quality", "delivery",
                                          "--workers", str(workers), *profile, "--strict", "--output", str(out.resolve())],
                             project, env, project / "render.log", timeout)
        if not out.is_file() or out.stat().st_size == 0:
            raise HyperframesError("HyperFrames returned without an MP4")
        info = await probe_video(out)
        streams = info.get("streams") or []
        if not streams or (streams[0].get("width"),streams[0].get("height")) != (1080,1920):
            raise HyperframesError("HyperFrames output resolution validation failed")
        if abs(float(info["format"]["duration"]) - export["total"]) > 0.12:
            raise HyperframesError("HyperFrames output duration validation failed")
    return out


def render_workers(options: dict) -> int:
    """Bound parallel capture inside the existing single-render OS lock."""
    workers=options.get('workers',1)
    if type(workers) is not int or workers not in (1,2):
        raise AdapterValidationError('HyperFrames workers must be 1 or 2')
    return 1 if options.get('low_memory') is True else workers
