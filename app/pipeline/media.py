"""ffmpeg/ffprobe 공통 유틸."""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path


def _find_ffmpeg_dir() -> str | None:
    """PATH 에 없으면 winget/chocolatey 설치 위치를 뒤져서 폴더를 돌려준다."""
    import os
    from pathlib import Path

    roots = [os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles"), os.environ.get("ProgramData")]
    patterns = [
        "Microsoft/WinGet/Packages/*FFmpeg*/**/bin/ffmpeg.exe",
        "Microsoft/WinGet/Links/ffmpeg.exe",
        "chocolatey/bin/ffmpeg.exe",
        "ffmpeg/bin/ffmpeg.exe",
    ]
    for r in roots:
        if not r:
            continue
        for pat in patterns:
            for hit in Path(r).glob(pat):
                if hit.exists() and (hit.parent / "ffprobe.exe").exists():
                    return str(hit.parent)
    return None


def require_ffmpeg() -> None:
    """ffmpeg/ffprobe 를 찾고, PATH 에 없으면 이 프로세스의 PATH 에 추가한다."""
    import os

    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return
    d = _find_ffmpeg_dir()
    if d:
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
        if shutil.which("ffmpeg") and shutil.which("ffprobe"):
            return
    raise RuntimeError("ffmpeg 를 찾을 수 없습니다. `winget install Gyan.FFmpeg` 로 설치한 뒤 프로그램을 다시 실행하세요.")


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        tail = "\n".join((p.stderr or "").strip().splitlines()[-15:])
        raise RuntimeError(f"{cmd[0]} 실패 (code {p.returncode}):\n{tail}")
    return p.stdout


async def run_ffmpeg(args: list[str], cwd: Path | None = None) -> None:
    await asyncio.to_thread(_run, ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], cwd)


def probe_duration_sync(path: Path) -> float:
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)])
    return float(json.loads(out)["format"]["duration"])


async def probe_duration(path: Path) -> float:
    return await asyncio.to_thread(probe_duration_sync, path)


def has_audio_sync(path: Path) -> bool:
    try:
        out = _run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                    "-show_entries", "stream=codec_type", "-of", "json", str(path)])
        return bool(json.loads(out).get("streams"))
    except Exception:  # noqa: BLE001
        return False


async def has_audio(path: Path) -> bool:
    """오디오 스트림이 있는지. 없는 소스에 [i:a] 를 쓰면 ffmpeg 가 실패한다."""
    return await asyncio.to_thread(has_audio_sync, path)


async def probe_video(path: Path) -> dict:
    out = await asyncio.to_thread(
        _run, ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(path)])
    return json.loads(out)


def ff_path(p: Path | str) -> str:
    """필터 문자열 안에 넣을 경로 이스케이프 (Windows 드라이브 콜론 포함)."""
    s = str(p).replace("\\", "/")
    return s.replace(":", "\\:").replace("'", "\\'")


async def extract_frames(video: Path, out_dir: Path, count: int = 3, max_width: int = 640) -> list[Path]:
    """영상에서 대표 프레임을 고르게 뽑는다 (비전 분석·썸네일용)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    dur = await probe_duration(video)
    # 맨 앞/뒤는 검은 화면인 경우가 많아 10~90% 구간에서 고른다
    spots = [dur * (0.1 + 0.8 * i / max(1, count - 1)) for i in range(count)] if count > 1 else [dur * 0.5]
    out: list[Path] = []
    for i, t in enumerate(spots):
        p = out_dir / f"{video.stem}_f{i}.jpg"
        try:
            await run_ffmpeg(["-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                              "-vf", f"scale={max_width}:-2", "-q:v", "4", str(p)])
            if p.exists():
                out.append(p)
        except RuntimeError:
            continue
    return out


async def concat_audio(parts: list[Path], out: Path, gap: float = 0.25, sample_rate: int = 24000) -> list[float]:
    """오디오 조각을 gap 초 무음을 끼워 이어붙이고, 각 조각의 시작 오프셋을 돌려준다."""
    durations = [await probe_duration(p) for p in parts]
    offsets: list[float] = []
    t = 0.0
    for d in durations:
        offsets.append(t)
        t += d + gap

    inputs: list[str] = []
    labels: list[str] = []
    filters: list[str] = []
    for i, p in enumerate(parts):
        inputs += ["-i", str(p)]
        filters.append(f"[{i}:a]aformat=sample_rates={sample_rate}:channel_layouts=mono,aresample={sample_rate}[a{i}]")
        labels.append(f"[a{i}]")
        if i < len(parts) - 1:
            filters.append(f"anullsrc=r={sample_rate}:cl=mono,atrim=0:{gap}[g{i}]")
            labels.append(f"[g{i}]")
    filters.append("".join(labels) + f"concat=n={len(labels)}:v=0:a=1[out]")
    await run_ffmpeg([*inputs, "-filter_complex", ";".join(filters), "-map", "[out]", "-c:a", "libmp3lame", "-q:a", "2", str(out)])
    return offsets
