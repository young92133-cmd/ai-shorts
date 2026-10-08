# Run the existing factory CLI without changing or reinstalling the project's environment.
$ErrorActionPreference = 'Stop'
$factoryArguments = $args
$projectRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$pythonWorks = $false
if (Test-Path -LiteralPath $taskPython) {
    try {
        & $taskPython -c 'import sys' *> $null
        $pythonWorks = $LASTEXITCODE -eq 0
    } catch { $pythonWorks = $false }
}
$previousPythonPath = $env:PYTHONPATH
$previousLocation = Get-Location
try {
    if (-not $pythonWorks) {
        $taskPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
        if (-not (Test-Path -LiteralPath $taskPython)) {
            throw '프로젝트 가상환경 Python을 찾을 수 없습니다. requirements.txt에 맞는 Python 환경을 준비해 주세요.'
        }
        $projectPackages = Join-Path $projectRoot '.venv\Lib\site-packages'
        $env:PYTHONPATH = if ($previousPythonPath) { "$projectPackages;$previousPythonPath" } else { $projectPackages }
    }
    Set-Location -LiteralPath $projectRoot
    & $taskPython -B -m app.factory @factoryArguments
    $factoryExit = $LASTEXITCODE
} finally {
    $env:PYTHONPATH = $previousPythonPath
    Set-Location -LiteralPath $previousLocation.Path
}
exit $factoryExit
