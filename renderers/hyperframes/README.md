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
one HyperFrames render, with one Chrome worker. Cancellation waits for its own
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
Key content occupies x < 930 and 250 ≤ y < 1520. Source images are contained,
not cropped, so existing baked-in text is also kept within the safe area.

Narration, BGM, source audio and optional `sfx: [{path,start,volume}]` are premixed
locally in a separate WAV. Optional `rendering.hyperframes.duck_bgm: true` enables
sidechain ducking only in this premix. It does not change the FFmpeg audio graph.
Original video offsets and limited `visual.play` durations are honored, freezing
the remaining frame where needed. Image zoom and slideshow crossfade timing
reuse the timeline; broll retains its original cut timing.

The completed same-content comparison and validation are recorded in
`docs/HYPERFRAMES_INTEGRATION_2026-11-09.md`. Economics/engineering presets and
`--variants` are not part of this stage. The environment remains pinned to 0.9.23;
the CLI's later-version notice does not upgrade it automatically.

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
