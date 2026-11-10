# Isolated local renderer tools. No Python, global npm, or persistent PATH changes.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$toolRoot = Join-Path $projectRoot '.tools\hyperframes'
$nodeExe = Join-Path $toolRoot 'node.exe'
$npmCli = Join-Path $toolRoot 'npm\bin\npm-cli.js'
$rendererRoot = Join-Path $projectRoot 'renderers\hyperframes'
$cli = Join-Path $rendererRoot 'node_modules\hyperframes\bin\hyperframes.mjs'
$toolArgs = @($args)
if (-not (Test-Path -LiteralPath $nodeExe)) { throw 'Project Node is missing; see renderers/hyperframes/README.md.' }
$previousLocation = Get-Location
$envNames = @('PATH', 'npm_config_cache', 'npm_config_userconfig', 'npm_config_globalconfig',
    'HYPERFRAMES_CACHE_DIR', 'HYPERFRAMES_CONFIG_DIR', 'HYPERFRAMES_SKIP_SKILLS', 'HYPERFRAMES_NO_TELEMETRY',
    'DO_NOT_TRACK', 'HYPERFRAMES_EXTRACT_CACHE_DIR', 'TEMP', 'TMP')
$saved = @{}
foreach ($name in $envNames) { $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    $env:PATH = $toolRoot + ';' + $env:PATH
    $env:npm_config_cache = Join-Path $toolRoot 'npm-cache'
    $env:npm_config_userconfig = Join-Path $toolRoot 'npmrc'
    $env:npm_config_globalconfig = Join-Path $toolRoot 'global-npmrc'
    $env:HYPERFRAMES_CACHE_DIR = Join-Path $toolRoot 'cache'
    $env:HYPERFRAMES_CONFIG_DIR = Join-Path $toolRoot 'config'
    $env:TEMP = Join-Path $toolRoot 'tmp'
    $env:TMP = $env:TEMP
    New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
    $env:HYPERFRAMES_SKIP_SKILLS = '1'
    $env:HYPERFRAMES_NO_TELEMETRY = '1'
    $env:HYPERFRAMES_EXTRACT_CACHE_DIR = Join-Path $toolRoot 'cache\extracted'
    $env:DO_NOT_TRACK = '1'
    Set-Location -LiteralPath $rendererRoot
    if ($toolArgs.Count -gt 0 -and $toolArgs[0] -eq 'npm') {
        & $nodeExe $npmCli @($toolArgs | Select-Object -Skip 1)
    } elseif ($toolArgs.Count -gt 0 -and $toolArgs[0] -eq 'npx') {
        & $nodeExe (Join-Path $toolRoot 'npm\bin\npx-cli.js') @($toolArgs | Select-Object -Skip 1)
    } elseif ($toolArgs.Count -gt 0 -and $toolArgs[0] -eq 'node') {
        & $nodeExe @($toolArgs | Select-Object -Skip 1)
    } else {
        & $nodeExe $cli @toolArgs
    }
    $toolExit = $LASTEXITCODE
} finally {
    Set-Location -LiteralPath $previousLocation.Path
    foreach ($name in $envNames) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
}
exit $toolExit
