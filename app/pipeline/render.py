"""ffmpeg 렌더링: (1) 이미지+나레이션 슬라이드쇼, (2) 원본 클립 이어붙이기."""
from __future__ import annotations

from pathlib import Path

from .media import ff_path, run_ffmpeg


def _subtitle_filter(ass_path: Path, fonts_dir: Path | None) -> str:
    f = f"ass='{ff_path(ass_path)}'"
    if fonts_dir and fonts_dir.exists():
        f += f":fontsdir='{ff_path(fonts_dir)}'"
    return f


def _audio_mix(narr_idx: int, bgm_idx: int | None, bgm_volume: float) -> str:
    if bgm_idx is None:
        return f"[{narr_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo[aout]"
    return (
        f"[{bgm_idx}:a]aloop=loop=-1:size=2147483647,volume={bgm_volume},aformat=sample_rates=44100:channel_layouts=stereo[bgm];"
        f"[{narr_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo[narr];"
        f"[narr][bgm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,afade=t=out:st=-2:d=2[aout]"
    )


async def render_slideshow(
    images: list[Path],
    durations: list[float],
    narration: Path,
    out_path: Path,
    ass_path: Path | None = None,
    bgm: Path | None = None,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    transition: float = 0.4,
    bgm_volume: float = 0.1,
    fonts_dir: Path | None = None,
) -> Path:
    """장면 이미지에 켄번즈 효과를 주고 xfade 로 이어붙인 뒤 오디오·자막을 얹는다.

    durations[i] 는 i번째 장면이 화면에 보여야 하는 시간(오디오 기준). 전환 시간은 내부에서 보정.
    """
    assert len(images) == len(durations) and images, "장면 수 불일치"
    n = len(images)
    xf = min(transition, min(durations) / 2) if n > 1 else 0.0

    args: list[str] = []
    filters: list[str] = []
    for i, (img, dur) in enumerate(zip(images, durations)):
        vis = dur + (xf if i < n - 1 else 0.0)
        frames = max(1, round(vis * fps))
        args += ["-loop", "1", "-framerate", str(fps), "-t", f"{vis + 0.5:.3f}", "-i", str(img)]
        # 번갈아 줌인/줌아웃. 확대해서 zoompan 하면 떨림이 줄어든다.
        if i % 2 == 0:
            z = f"1+0.12*on/{frames}"
        else:
            z = f"1.12-0.12*on/{frames}"
        filters.append(
            f"[{i}:v]scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase,crop={width * 2}:{height * 2},"
            f"zoompan=z='{z}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps},"
            f"trim=duration={vis:.3f},setpts=PTS-STARTPTS,format=yuv420p[v{i}]"
        )

    # xfade 체인: offset_k = sum(durations[:k])
    if n == 1:
        last = "[v0]"
    else:
        prev = "[v0]"
        acc = 0.0
        for k in range(1, n):
            acc += durations[k - 1]
            out = f"[x{k}]" if k < n - 1 else "[vcat]"
            filters.append(f"{prev}[v{k}]xfade=transition=fade:duration={xf:.3f}:offset={acc:.3f}{out}")
            prev = out
        last = "[vcat]"

    narr_idx = n
    args += ["-i", str(narration)]
    bgm_idx = None
    if bgm and bgm.exists():
        bgm_idx = n + 1
        args += ["-i", str(bgm)]
    filters.append(_audio_mix(narr_idx, bgm_idx, bgm_volume))

    if ass_path:
        filters.append(f"{last}{_subtitle_filter(ass_path, fonts_dir)}[vout]")
        last = "[vout]"

    await run_ffmpeg([
        *args,
        "-filter_complex", ";".join(filters),
        "-map", last, "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", "-shortest",
        str(out_path),
    ], cwd=out_path.parent)
    return out_path


async def render_clips(
    source: Path,
    segments: list[tuple[float, float]],
    out_path: Path,
    ass_path: Path | None = None,
    bgm: Path | None = None,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    bgm_volume: float = 0.08,
    blur_background: bool = True,
    fonts_dir: Path | None = None,
) -> Path:
    """원본 가로 영상에서 구간을 잘라 9:16 으로 만든다.

    blur_background=True: 원본을 블러 배경으로 깔고 가운데 원본을 맞춰 넣음(잘림 없음).
    False: 중앙 크롭.
    """
    filters: list[str] = []
    vlabels: list[str] = []
    alabels: list[str] = []
    for i, (s, e) in enumerate(segments):
        if blur_background:
            filters.append(
                f"[0:v]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS,split[c{i}][b{i}];"
                f"[b{i}]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=30:10[bg{i}];"
                f"[c{i}]scale={width}:-2[fg{i}];"
                f"[bg{i}][fg{i}]overlay=(W-w)/2:(H-h)/2,fps={fps},format=yuv420p[v{i}]"
            )
        else:
            filters.append(
                f"[0:v]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS,"
                f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={fps},format=yuv420p[v{i}]"
            )
        filters.append(f"[0:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo[a{i}]")
        vlabels.append(f"[v{i}]")
        alabels.append(f"[a{i}]")

    filters.append("".join(f"{v}{a}" for v, a in zip(vlabels, alabels)) + f"concat=n={len(segments)}:v=1:a=1[vcat][acat]")
    last = "[vcat]"

    args = ["-i", str(source)]
    if bgm and bgm.exists():
        args += ["-i", str(bgm)]
        filters.append(
            f"[1:a]aloop=loop=-1:size=2147483647,volume={bgm_volume},aformat=sample_rates=44100:channel_layouts=stereo[bgm];"
            f"[acat][bgm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
        )
    else:
        filters.append("[acat]anull[aout]")

    if ass_path:
        filters.append(f"{last}{_subtitle_filter(ass_path, fonts_dir)}[vout]")
        last = "[vout]"

    await run_ffmpeg([
        *args,
        "-filter_complex", ";".join(filters),
        "-map", last, "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_path),
    ], cwd=out_path.parent)
    return out_path


def _ninefix(src: str, out: str, width: int, height: int, fps: int, blur: bool) -> str:
    """가로 영상을 9:16 으로. blur=True 면 블러 배경 위에 원본을 얹어 잘림이 없다."""
    if blur:
        return (
            f"{src}split[c_{out}][b_{out}];"
            f"[b_{out}]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},boxblur=30:10[bg_{out}];"
            f"[c_{out}]scale={width}:-2[fg_{out}];"
            f"[bg_{out}][fg_{out}]overlay=(W-w)/2:(H-h)/2,fps={fps},format=yuv420p[{out}]"
        )
    return (f"{src}scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps={fps},format=yuv420p[{out}]")


async def render_broll(
    clips: list[dict],
    narration: Path,
    out_path: Path,
    ass_path: Path | None = None,
    bgm: Path | None = None,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    bgm_volume: float = 0.06,
    source_volume: float = 0.12,
    blur_background: bool = True,
    fonts_dir: Path | None = None,
) -> Path:
    """여러 소스 영상·이미지를 장면 순서대로 이어 붙이고 나레이션을 얹는다.

    clips 의 각 항목:
      {"kind": "video", "path": Path, "start": float, "duration": float, "has_audio": bool}
      {"kind": "image", "path": Path, "duration": float}

    각 클립은 duration 에 **정확히** 맞춰진다. 영상이 모자라면 마지막 프레임을 유지(tpad)한다.
    원본 소리는 source_volume 으로 줄여 깔고, 나레이션은 원본 크기로 위에 얹는다.
    """
    assert clips, "클립이 없습니다"

    # 같은 파일을 여러 번 써도 입력은 하나만
    inputs: list[str] = []
    index_of: dict[str, int] = {}

    def input_index(path: Path, image: bool, dur: float) -> int:
        key = f"{'i' if image else 'v'}:{path}:{dur if image else ''}"
        if key in index_of:
            return index_of[key]
        if image:
            inputs.extend(["-loop", "1", "-framerate", str(fps), "-t", f"{dur + 0.5:.3f}", "-i", str(path)])
        else:
            inputs.extend(["-i", str(path)])
        index_of[key] = len(index_of)
        return index_of[key]

    filters: list[str] = []
    vlabels: list[str] = []
    alabels: list[str] = []

    for k, c in enumerate(clips):
        dur = float(c["duration"])
        vl, al = f"v{k}", f"a{k}"

        if c["kind"] == "image":
            idx = input_index(Path(c["path"]), True, dur)
            frames = max(1, round(dur * fps))
            zoom = f"1+0.10*on/{frames}" if k % 2 == 0 else f"1.10-0.10*on/{frames}"
            filters.append(
                f"[{idx}:v]scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase,"
                f"crop={width * 2}:{height * 2},"
                f"zoompan=z='{zoom}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps},"
                f"trim=duration={dur:.3f},setpts=PTS-STARTPTS,format=yuv420p[{vl}]"
            )
            filters.append(f"anullsrc=r=44100:cl=stereo,atrim=duration={dur:.3f},asetpts=PTS-STARTPTS[{al}]")
        else:
            idx = input_index(Path(c["path"]), False, dur)
            s = float(c.get("start", 0.0))
            e = s + dur
            # 원본이 모자랄 수 있으니 뒤를 마지막 프레임으로 채운 뒤 정확히 자른다
            filters.append(
                f"[{idx}:v]trim={s:.3f}:{e + 1.0:.3f},setpts=PTS-STARTPTS,"
                f"tpad=stop_mode=clone:stop_duration={dur:.3f},"
                f"trim=duration={dur:.3f},setpts=PTS-STARTPTS[raw{k}]"
            )
            filters.append(_ninefix(f"[raw{k}]", vl, width, height, fps, blur_background))

            if c.get("has_audio"):
                filters.append(
                    f"[{idx}:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS,"
                    f"apad=pad_dur={dur:.3f},atrim=duration={dur:.3f},asetpts=PTS-STARTPTS,"
                    f"volume={source_volume},aformat=sample_rates=44100:channel_layouts=stereo[{al}]"
                )
            else:
                filters.append(f"anullsrc=r=44100:cl=stereo,atrim=duration={dur:.3f},asetpts=PTS-STARTPTS[{al}]")

        vlabels.append(f"[{vl}]")
        alabels.append(f"[{al}]")

    filters.append("".join(f"{v}{a}" for v, a in zip(vlabels, alabels))
                   + f"concat=n={len(clips)}:v=1:a=1[vcat][acat]")

    narr_idx = len(index_of)
    inputs.extend(["-i", str(narration)])
    filters.append(f"[{narr_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo[narr]")
    mix = "[acat][narr]"
    n_mix = 2

    if bgm and bgm.exists():
        inputs.extend(["-i", str(bgm)])
        filters.append(
            f"[{narr_idx + 1}:a]aloop=loop=-1:size=2147483647,volume={bgm_volume},"
            f"aformat=sample_rates=44100:channel_layouts=stereo[bgm]")
        mix += "[bgm]"
        n_mix = 3

    filters.append(f"{mix}amix=inputs={n_mix}:duration=first:dropout_transition=0:normalize=0,"
                   f"afade=t=out:st=-1.5:d=1.5[aout]")

    last = "[vcat]"
    if ass_path:
        filters.append(f"{last}{_subtitle_filter(ass_path, fonts_dir)}[vout]")
        last = "[vout]"

    await run_ffmpeg([
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", last, "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", "-shortest",
        str(out_path),
    ], cwd=out_path.parent)
    return out_path


async def make_thumbnail(video: Path, out_path: Path, at: float = 1.0) -> Path:
    await run_ffmpeg(["-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1", "-q:v", "3", str(out_path)])
    return out_path
