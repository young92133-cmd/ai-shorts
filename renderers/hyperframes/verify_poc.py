"""Verify the encoded PoC, including all-frame safe zones and actual motion."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output" / "hyperframes-poc-20261108"
MOVIE = OUT / "hyperframes-poc-10s.mp4"
FONT = ROOT / "renderers" / "hyperframes" / "poc" / "assets" / "fonts" / "NotoSansKR-VF.ttf"
WIDTH, HEIGHT, FPS = 1080, 1920, 30


def main() -> None:
    assert MOVIE.is_file() and MOVIE.stat().st_size > 0, "Missing MP4"
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(MOVIE)]))
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    audio = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    assert (video["width"], video["height"], video["r_frame_rate"]) == (WIDTH, HEIGHT, "30/1")
    assert video["codec_name"] == "h264" and video["pix_fmt"] == "yuv420p"
    assert audio["codec_name"] == "aac" and int(audio["sample_rate"]) == 48000
    assert int(video["nb_read_frames"]) == 300
    assert abs(float(probe["format"]["duration"]) - 10) <= 1 / FPS
    assert abs(float(audio["duration"]) - 10) <= 1 / FPS
    (OUT / "ffprobe.json").write_text(json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")

    frame_dir = OUT / "frames"; frame_dir.mkdir(exist_ok=True)
    count_frames = [42, 62, 81, 101, 120]
    save_indices = set(count_frames + [0, 30, 135, 150, 165, 180, 210, 270])
    saved = {}
    heights = []
    unsafe = []
    bar_colors = np.array([[139, 163, 175], [169, 192, 202], [167, 232, 211]], dtype=np.int16)
    decoder = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(MOVIE), "-an",
                                "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], stdout=subprocess.PIPE)
    i = 0
    while True:
        data = decoder.stdout.read(WIDTH * HEIGHT * 3)
        if not data:
            break
        assert len(data) == WIDTH * HEIGHT * 3, "Truncated decoded frame"
        rgb = np.frombuffer(data, dtype=np.uint8).reshape(HEIGHT, WIDTH, 3)
        ground = rgb[10, 10].astype(np.int16)
        zones = [rgb[:250], rgb[1520:], rgb[250:1520, 930:]]
        changed = sum(int(np.count_nonzero(np.max(np.abs(z.astype(np.int16) - ground), axis=2) > 35)) for z in zones)
        if changed:
            unsafe.append({"frame": i, "pixels": changed})
        frame_heights = []
        for x, color in zip([201, 461, 721], bar_colors):
            strip = rgb[1000:1305, x-12:x+12].astype(np.int16)
            mask = np.max(np.abs(strip - color), axis=2) < 18
            # Count only the solid run touching the baseline. Fading text above a
            # bar can briefly share its RGB color and must not count as its height.
            rows = np.count_nonzero(mask, axis=1) >= 12
            first_gap = np.flatnonzero(~rows[::-1])
            frame_heights.append(int(first_gap[0]) if len(first_gap) else len(rows))
        heights.append(frame_heights)
        if i in save_indices:
            saved[i] = Image.fromarray(rgb.copy())
        if i in [30, 150, 270]:
            saved[i].save(frame_dir / f"{i//30:02d}s.png")
        i += 1
    assert decoder.wait() == 0 and i == 300
    assert not unsafe, f"Unsafe pixels found: {unsafe[:5]}"

    # Check actual decoded glyph shapes change throughout the count, not only the HTML.
    count_crops = [saved[n].crop((90, 620, 470, 840)) for n in count_frames]
    crop_hashes = [hashlib.sha256(c.tobytes()).hexdigest() for c in count_crops]
    assert len(set(crop_hashes)) == len(count_frames), "Counter crops did not all change"
    crop_differences = [float(np.mean(np.abs(np.asarray(a).astype(np.int16) - np.asarray(b).astype(np.int16))))
                        for a, b in zip(count_crops, count_crops[1:])]
    assert all(d > 1 for d in crop_differences), "Counter did not visibly change"
    levels = np.array(heights)
    first_growth = [next(n for n, h in enumerate(levels[:, k]) if h >= 3) for k in range(3)]
    assert first_growth[0] < first_growth[1] < first_growth[2]
    assert all(abs(int(v) - expected) <= 3 for v, expected in zip(levels[270], [96, 168, 240]))
    assert np.all(levels[123] == 0) and levels[135, 0] > 30 and np.all(levels[135, 1:] == 0)
    assert levels[165, 1] > 60 and levels[165, 2] == 0 and levels[180, 2] > 30
    (OUT / "bar-motion-samples.json").write_text(json.dumps(heights), encoding="utf-8")
    reversals = np.argwhere(np.diff(levels, axis=0) < -2)
    assert len(reversals) == 0, f"Bars rewound: {[(int(n), int(k), levels[n].tolist(), levels[n+1].tolist()) for n,k in reversals[:8]]}"
    title_delta = float(np.mean(np.abs(np.asarray(saved[0].crop((90, 350, 880, 550))).astype(np.int16)
                                      - np.asarray(saved[30].crop((90, 350, 880, 550))).astype(np.int16))))
    transition_delta = float(np.mean(np.abs(np.asarray(saved[210].crop((90, 350, 880, 550))).astype(np.int16)
                                           - np.asarray(saved[270].crop((90, 350, 880, 550))).astype(np.int16))))
    assert title_delta > 1 and transition_delta > 1
    pcm = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(MOVIE),
                                   "-vn", "-f", "f32le", "-acodec", "pcm_f32le", "pipe:1"])
    signal = np.frombuffer(pcm, dtype="<f4")
    rms = float(np.sqrt(np.mean(signal * signal)))
    peak = float(np.max(np.abs(signal)))
    assert rms > 1e-5 and peak < 0.95, "Silent or clipped test audio"

    label_font = ImageFont.truetype(str(FONT), 26)
    contact = Image.new("RGB", (1128, 700), "#f4f2e9")
    draw = ImageDraw.Draw(contact)
    for j, frame in enumerate([30, 150, 270]):
        draw.text((16 + j*376, 8), f"{frame//30}초", font=label_font, fill="#101e25")
        contact.paste(saved[frame].resize((360, 640), Image.Resampling.LANCZOS), (8+j*376, 51))
    contact.save(OUT / "comparison-1s-5s-9s.png")
    counter_strip = Image.new("RGB", (1280, 195), "#101e25")
    draw = ImageDraw.Draw(counter_strip)
    for j, (frame, crop) in enumerate(zip(count_frames, count_crops)):
        counter_strip.paste(crop.resize((250, 145), Image.Resampling.LANCZOS), (j*256, 42))
        draw.text((j*256+8, 4), f"{frame/FPS:.2f}초", font=label_font, fill="#f4f2e9")
    counter_strip.save(OUT / "counter-motion.png")

    reports = ROOT / "renderers" / "hyperframes" / "poc" / ".hyperframes" / "artifacts" / "checks"
    check_file = max(reports.glob("*.json"), key=lambda p: p.stat().st_mtime)
    check = json.loads(check_file.read_text(encoding="utf-8"))
    categories = ["lint", "runtime", "layout", "motion", "contrast", "craft", "audio"]
    assert check["ok"] and all(check[c]["errorCount"] == 0 and check[c]["warningCount"] == 0 for c in categories)
    (OUT / "hyperframes-check.json").write_text(json.dumps(check, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {"ok": True, "video": {k: video[k] for k in ["codec_name", "width", "height", "pix_fmt", "r_frame_rate", "nb_read_frames", "duration"]},
              "audio": {"codec_name": audio["codec_name"], "sample_rate": audio["sample_rate"],
                        "channels": audio["channels"], "duration": audio["duration"], "decoded_rms": rms, "decoded_peak": peak},
              "safety": {"frames_checked": i, "safe_box": {"x_min": 0, "x_max_exclusive": 930, "y_min": 250, "y_max_exclusive": 1520},
                         "unsafe_pixel_frames": unsafe, "pixel_background_tolerance": 35},
              "counter": {"frames": count_frames, "times": [n/FPS for n in count_frames], "distinct_crops": len(set(crop_hashes)),
                          "consecutive_mean_pixel_differences": crop_differences, "comparison": "counter-motion.png"},
              "bars": {"first_visible_frame": first_growth, "first_visible_seconds": [n/FPS for n in first_growth],
                       "final_decoded_heights_px": levels[270].tolist(), "expected_heights_px": [96, 168, 240], "sequential_growth_verified": True},
              "title_entrance_mean_pixel_change": title_delta, "scene_transition_mean_pixel_change": transition_delta,
              "strict_check": {c: {k: check[c][k] for k in ["ok", "errorCount", "warningCount"]} for c in categories},
              "snapshots": ["frames/01s.png", "frames/05s.png", "frames/09s.png"]}
    (OUT / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
