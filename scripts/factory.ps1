# Run the existing factory CLI; preserve the original environment and process PATH.
$ErrorActionPreference = 'Stop'
$factoryArguments = $args
$projectRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$recoveredPython = Join-Path (Split-Path -Parent $projectRoot) '.codex-envs\ai-shorts-py312\Scripts\python.exe'
$pythonWorks = $false
if (Test-Path -LiteralPath $taskPython) {
    try {
        & $taskPython -c 'import sys' *> $null
        $pythonWorks = $LASTEXITCODE -eq 0
    } catch { $pythonWorks = $false }
}
$previousPythonPath = $env:PYTHONPATH
$previousPath = $env:PATH
$previousLocation = Get-Location
try {
    if (-not $pythonWorks -and (Test-Path -LiteralPath $recoveredPython)) {
        & $recoveredPython -B -c 'import sys' *> $null
        if ($LASTEXITCODE -eq 0) {
            $taskPython = $recoveredPython
            $pythonWorks = $true
        }
    }
    if (-not $pythonWorks) {
        $taskPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
        if (-not (Test-Path -LiteralPath $taskPython)) {
            throw '프로젝트 가상환경 Python을 찾을 수 없습니다. requirements.txt에 맞는 Python 환경을 준비해 주세요.'
        }
        $projectPackages = Join-Path $projectRoot '.venv\Lib\site-packages'
    }
    if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or
        -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
        $localFfmpeg = Get-ChildItem -LiteralPath (Split-Path -Parent $projectRoot) -Directory -Filter 'ffmpeg*' |
            Sort-Object Name -Descending | Where-Object {
                (Test-Path -LiteralPath (Join-Path $_.FullName 'bin\ffmpeg.exe')) -and
                (Test-Path -LiteralPath (Join-Path $_.FullName 'bin\ffprobe.exe'))
            } | Select-Object -First 1
        if ($localFfmpeg) { $env:PATH = (Join-Path $localFfmpeg.FullName 'bin') + ';' + $previousPath }
    }
    Set-Location -LiteralPath $projectRoot
    if ($pythonWorks) {
        & $taskPython -B -m app.factory @factoryArguments
    } else {
        # addsitedir processes .pth files (including pywin32); PYTHONPATH alone does not.
        & $taskPython -B -c 'import sys,site,runpy; site.addsitedir(sys.argv.pop(1)); sys.argv[0]="app.factory"; runpy.run_module("app.factory",run_name="__main__")' $projectPackages @factoryArguments
    }
    $factoryExit = $LASTEXITCODE
} finally {
    $env:PYTHONPATH = $previousPythonPath
    $env:PATH = $previousPath
    Set-Location -LiteralPath $previousLocation.Path
}
exit $factoryExit
