# HyperFrames optional renderer

Stage one remains preserved under `poc/`. Stage two adds an optional adapter at
`app/pipeline/hyperframes.py`, selected by the existing factory CLI. The original
FFmpeg rendering functions and TTS implementation are unchanged.

## Pipeline use (stage two)

```powershell
./scripts/factory.ps1 make --topic "주제" --renderer hyperframes --review
./scripts/factory.ps1 rerender PROJECT_ID --renderer hyperframes
./scripts/factory.ps1 rerender PROJECT_ID --renderer ffmpeg
# Explicitly enable fallback; the default is none.
./scripts/factory.ps1 rerender PROJECT_ID --renderer hyperframes --renderer-fallback ffmpeg
```

FFmpeg remains the default in `config.yaml` (`rendering.renderer`). New timelines
may carry an optional `render` settings object; V1 timelines without it remain
compatible. The HyperFrames HTML, asset manifest and caption map are **derived
output**, not a second content input format. Rerenders never replace the previous
`final.mp4`, thumbnail or timeline. New videos live under `PROJECT/renders/` and
the CLI returns their actual paths. The project state/UI points to the new result.

Each attempt retains `render-result.json`; each successful output has a
`.render.json` sidecar with requested/actual renderer, fallback, errors and time.
Invalid paths/data never trigger fallback. Missing local tools or failed local
HyperFrames commands may fall back only when explicitly enabled. Failures keep
the old delivery and their local logs. A process-wide OS file lock permits only
one HyperFrames render, with a bounded one or two capture workers. Cancellation waits for its own
Node/Chrome process tree to stop before releasing the slot.

Input assets are limited to the job, repository `assets/`, and explicit trusted
`rendering.hyperframes.asset_roots`. URLs, UNC/device paths, drive-relative paths,
traversal/symlink escapes and unsupported file types are rejected. Copied assets
use hashed relative names. Screen strings are escaped for HTML and never put
into executable JavaScript. Source registry checks remain enabled.

Saved word timestamps are reused verbatim. Captions wrap around 14 characters
at word/sentence boundaries into at most two rows; a long word is fitted, never
cut. With no word timestamps a legacy cue stays static instead of inventing
speech alignment. Noto Sans KR is reused from the preserved PoC assets.
Key text occupies x < 930 and 250 ≤ y < 1520 by default. Stage three's
`rendering.hyperframes.layout: adaptive` fills the background independently of
this text-safe box (`safe_area: {left: 72, top: 250, right: 150, bottom: 400}`).
Use `layout: legacy` for the original stage-two placement.

Narration, BGM, source audio and optional `sfx: [{path,start,volume}]` are premixed
locally when mixing is needed. Adaptive voice-only exports reuse the copied
original audio directly, skipping a redundant WAV. Optional `rendering.hyperframes.duck_bgm: true` enables
sidechain ducking only in this premix. It does not change the FFmpeg audio graph.
Original video offsets and limited `visual.play` durations are honored, freezing
the remaining frame where needed. Image zoom and slideshow crossfade timing
reuse the timeline; matching saved blueprint fade hints may enrich adaptive
presentation without changing scene or speech clocks.

The completed same-content comparison and validation are recorded in
`docs/HYPERFRAMES_INTEGRATION_2026-11-09.md`. Economics/engineering presets and
`--variants` are not part of this stage. The environment remains pinned to 0.9.23;
the CLI's later-version notice does not upgrade it automatically.

## Adaptive presentation (stage three)

`app/pipeline/hyperframes_layout.py` verifies optional local blueprint/script
hints against the saved scene's timing, asset identity and wording. Only an
existing rights-registered generated card can become native HTML text. Missing
or stale hints retain the raster. A composited photo can reuse its exact
rights-checked parent, with matching attribution and the same path safeguards.
No new material is downloaded, and no input timeline/sidecar is rewritten.

Headings, comparison labels, existing key numbers, underline/arrow reveals and
explicit step-count diagrams are separate HTML layers. Diagram heights are
decorative and labelled accordingly; statistics are never invented. Static
background decoration reuses the Shorts graphics helper once per export.
Large portrait photos allow a bounded center crop; wide/small photos retain
the entire subject above a preblurred full-screen background. Small photos
are capped at 2.5× base foreground enlargement plus at most 1.8% gentle motion.
Landscape video retains its original
aspect and decoding resolution, with a static first-frame blurred backdrop.
Timed video remains a direct stage child, as required by official lint.

`cache_media: true` caches completed video derivatives by source SHA, original
offset/play/duration and conversion settings under `.tools/hyperframes/cache/`.
One concurrent render remains mandatory. `low_memory: false` keeps the normal
capture path; forcing screenshot safe mode was slower in the actual comparison
and showed no reliable memory advantage in provisional sampling. Resolution and delivery quality
are unchanged. See `docs/HYPERFRAMES_STAGE3_2026-11-10.md` for measured tradeoffs.

```powershell
# New report directory protects earlier comparisons; uses saved content only.
../shorts-ai/.venv/Scripts/python.exe -B scripts/compare_renderers.py --renderer hyperframes --report output/my-new-comparison
./scripts/hyperframes.ps1 check ABSOLUTE_GENERATED_PROJECT --strict --json
./.tools/hyperframes/node.exe scripts/verify_hyperframes_layout.mjs ABSOLUTE_GENERATED_PROJECT output/my-new-comparison/layout-audit.json
../shorts-ai/.venv/Scripts/python.exe -B scripts/verify_hyperframes_stage3.py --report output/my-new-comparison
```

The DOM audit checks every output frame's key-text ranges, Korean font loading
and title/caption separation. The MP4 audit independently probes the delivery,
checks actual highlight/animation pixels and voice correlation, preserves A/B
hashes and produces contact sheets. Background pixels may cross safety guides;
the stage-two all-foreground pixel assertion is intentionally not used here.
Measurement v2 filters process ancestry by creation time as well as PID to
exclude unrelated processes after Windows PID reuse; historical A/B metrics
used the older PID-only sampler, limiting strict CPU/memory comparability.

## Capture performance (stage 3.1)

`rendering.hyperframes.workers` accepts only 1 or 2; omitted settings retain 1.
The current 32 GB PC configuration uses **2** for faster parallel software
capture. `low_memory: true` pins the passed worker count to 1. The OS lock still
allows only one render job at a time. Use `workers: 1` to reduce memory.

Paired debug runs averaged 88.639 → 67.052 seconds, with unchanged visual HTML,
caption clocks and delivery encoder quality. Memory increased to about 2.9 GiB.
The actual normal CLI delivery took 68.589 seconds / 2.896 GiB; both the
60-second / 2.2-GiB and 40-second / 2-GiB targets remain unmet. Two workers select
the official parallel screenshot path, while the prior one-worker run used
drawElement. Full-frame SSIM 0.998259 / PSNR 52.419 dB, exact caption timestamps,
actual highlight checks and visual contact sheets verified preservation.

No animations were removed, and resolution/CRF were not reduced. Software
H.264 remains the default; AMD AMF encoding was confirmed in a separate trial
but not adopted. The unsuccessful image-sequence experiments are retained only
in Git-ignored output, not in production source. Caption measurement reuses the
existing Noto 700-weight font cache without changing fitted geometry.

```powershell
# A fresh report directory is required. Rerender only: no script/TTS generation.
../shorts-ai/.venv/Scripts/python.exe -B scripts/profile_hyperframes.py --report output/new-profile --debug --workers 2
# Optional diagnostic-only Page RPC timing, not used in production renders.
../shorts-ai/.venv/Scripts/python.exe -B scripts/profile_hyperframes.py --report output/new-rpc-profile --debug --rpc-profile
```

The profiler records official engine phases, adapter stages, process CPU/memory
and logical I/O, plus system CPU/physical-disk context. Logical process I/O
includes pipes; system disk rates cannot be attributed exclusively to the
render. Overlapping capture/encode intervals are not additive. See
`docs/HYPERFRAMES_PERFORMANCE_2026-11-11.md` for every trial, measurement limits,
backups, output paths and remaining bottlenecks. Node/HyperFrames packages and
the pinned installation remain unchanged.

## Installed environment (2026-11-08)

| Component | Version | Location, relative to repository root |
| --- | --- | --- |
| Node | 24.22.1 | `.tools/hyperframes/node.exe` (copy of the existing Codex runtime) |
| npm / npx | 12.2.2 | `.tools/hyperframes/npm/bin/{npm,npx}-cli.js` |
| HyperFrames | **0.9.23** | `renderers/hyperframes/node_modules/hyperframes/` |
| GSAP | **3.14.2** | `node_modules/gsap/`, copied into `poc/assets/vendor/` |
| Chrome Headless Shell | 152.0.7977.30 | `.tools/hyperframes/cache/chrome/` |
| FFmpeg / ffprobe | 9.0.1 | Existing Windows WinGet installation; unchanged |
| Noto Sans KR | Existing variable font | `poc/assets/fonts/NotoSansKR-VF.ttf`, copied from Windows Fonts |

The npm bootstrap tarball was verified against its official SHA-512 integrity
value. Exact npm and Node hashes are in `.tools/hyperframes/installation.json`
and the result folder's `installation.json`. Node 24.22.1 satisfies npm 12.2.2's
`^24.15.0` engine requirement and HyperFrames' `>=22` requirement.

The official 0.9.20–0.9.23 release notes include Korean number/counter reading,
seek/render timing, and fade-in completion fixes. These directly concern this
PoC, so 0.9.23 was selected instead of 0.9.19. Dependencies and the PoC registry
ref are pinned. No agent skills or Claude Code plugin were installed.

## Reconstruct the ignored tools on Windows

Run from this repository root. This installs only into `.tools/hyperframes`;
it does not alter the system PATH, Python environment, or FFmpeg installation.
The font (with OFL), GSAP vendor source, and local test tone are tracked PoC assets.

```powershell
$tool = Join-Path (Get-Location) '.tools/hyperframes'
New-Item -ItemType Directory -Force -Path $tool | Out-Null
$bundled = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
if ((Test-Path -LiteralPath $bundled) -and ((& $bundled --version) -eq 'v24.22.1')) {
  Copy-Item -LiteralPath $bundled -Destination (Join-Path $tool 'node.exe')
} else {
  $archive = 'node-v24.22.1-win-x64.zip'
  Invoke-WebRequest "https://nodejs.org/dist/v24.22.1/$archive" -OutFile (Join-Path $tool $archive)
  $sums = (Invoke-WebRequest 'https://nodejs.org/dist/v24.22.1/SHASUMS256.txt').Content
  $expected = (($sums -split "`n" | Where-Object { $_.Trim().EndsWith($archive) }) -split '\s+')[0]
  if ((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $tool $archive)).Hash -ne $expected) { throw 'Node checksum mismatch' }
  Expand-Archive -LiteralPath (Join-Path $tool $archive) -DestinationPath (Join-Path $tool 'node-distribution')
  Copy-Item -LiteralPath (Join-Path $tool 'node-distribution/node-v24.22.1-win-x64/node.exe') -Destination (Join-Path $tool 'node.exe')
}
$meta = Invoke-RestMethod 'https://registry.npmjs.org/npm/12.2.2'
Invoke-WebRequest $meta.dist.tarball -OutFile (Join-Path $tool 'npm.tgz')
$expected = [Convert]::ToHexString([Convert]::FromBase64String(($meta.dist.integrity -replace '^sha512-','')))
if ((Get-FileHash -Algorithm SHA512 -LiteralPath (Join-Path $tool 'npm.tgz')).Hash -ne $expected) { throw 'npm checksum mismatch' }
New-Item -ItemType Directory -Force -Path (Join-Path $tool 'npm') | Out-Null
tar -xzf (Join-Path $tool 'npm.tgz') --strip-components=1 -C (Join-Path $tool 'npm')
'audit=false','fund=false','registry=https://registry.npmjs.org/','update-notifier=false' | Set-Content (Join-Path $tool 'npmrc')
'' | Set-Content (Join-Path $tool 'global-npmrc')
./scripts/hyperframes.ps1 npm ci --no-audit --no-fund
./scripts/hyperframes.ps1 browser ensure
```

The registry bootstrap and browser step require network access. Nothing installs
a Claude Code plugin or coding-agent skills. If restoring only source from Git,
actual deliveries and measurements under `output/` remain local; their verified
hashes and results are preserved in the stage-one/stage-two reports.

## Run from the repository root

```powershell
# The wrapper uses project Node/npm and restores the caller's environment.
./scripts/hyperframes.ps1 node --version
./scripts/hyperframes.ps1 npm --version
./scripts/hyperframes.ps1 npx --version
./scripts/hyperframes.ps1 lint poc --json
./scripts/hyperframes.ps1 check poc --json --strict --at '0,1,2.7,5,7,9'

# Optional local editor (stop after review).
./scripts/hyperframes.ps1 preview poc --background --no-open --port 3017
./scripts/hyperframes.ps1 preview poc --stop

# Explicit rendering; this is separate from app.factory.
./scripts/hyperframes.ps1 render poc --fps 30 --quality delivery --workers 2 --strict --output ../../output/hyperframes-poc-20261108/recheck.mp4

# Verify the already-created delivery, using the existing shared Python.
../shorts-ai/.venv/Scripts/python.exe -B renderers/hyperframes/verify_poc.py
```

`measure_render.py` measures a render process and its descendants, saves the
raw samples and logs, and renders to the original PoC delivery filename. Preserve
the existing output before deliberately rerunning that measurement. Its Windows
memory sampler uses only Python's standard library; the output verifier uses
the already-installed NumPy and Pillow. No Python packages were installed.

Local npm commands are available through the wrapper, not a global npm install.
`npm ci --no-audit --no-fund` through this wrapper restores the exact Node
dependency tree. npm 12 blocked esbuild's optional postinstall by default; the
platform binary was present and the actual checks/render succeeded without
approving additional installation scripts.

## Rendering and verification

The 10-second composition is 1080×1920 at 30 fps. It has a Korean title reveal,
0→100 count, three sequential bars, a closing crossfade, and a local 330 Hz test
tone. All text uses the copied Noto Sans KR font through a local `@font-face`.
GSAP and fonts are local assets, so the composition itself has no CDN requests.
The bar layout adapts the official `animated-bar-chart` catalog component.

Key text stays within x < 930 and 250 ≤ y < 1520. The verifier checks every
decoded MP4 frame for foreground pixels in the excluded top/bottom/right zones,
plus actual counter crop changes, sequential bar growth, title/transition frame
differences, non-silent/non-clipping decoded audio, and the strict check report.
This complements the browser's layout and contrast checks; it is not an OCR
claim. The counter strip and 1/5/9-second frames were also inspected visually.

Output is under `output/hyperframes-poc-20261108/` (Git-ignored). See
`docs/HYPERFRAMES_POC_2026-11-08.md` for measured results and remaining work.

The wrapper now isolates cache, configuration, temporary files, and npm settings
under `.tools/hyperframes/`, disables telemetry, and restores process variables.
The initial official CLI bootstrap also created local install/run metadata in
`~/.hyperframes/`; it was preserved rather than deleting user-home state.

## Sources and licenses

- [Official README, pinned release](https://github.com/heygen-com/hyperframes/blob/v0.9.23/README.md)
- [0.9.23 release](https://github.com/heygen-com/hyperframes/releases/tag/v0.9.23)
- [Official bar component](https://github.com/heygen-com/hyperframes/blob/v0.9.23/registry/components/animated-bar-chart/animated-bar-chart.html)
- [Noto Sans KR / SIL OFL](https://github.com/google/fonts/tree/main/ofl/notosanskr), license copied to `poc/assets/fonts/OFL.txt`
- [GSAP license](https://gsap.com/standard-license/); the vendor copy retains its copyright/license header and upstream README.
