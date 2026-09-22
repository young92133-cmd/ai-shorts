@echo off
cd /d "%~dp0"
set CLAUDECODE=
set CLAUDE_CODE_ENTRYPOINT=
set "CLI="
for /f "delims=" %%F in ('dir /b /s /o-d "%APPDATA%\Claude\claude-code\claude.exe" 2^>nul') do if not defined CLI set "CLI=%%F"
if not defined CLI (
  echo claude.exe not found. Install: irm https://claude.ai/install.ps1 ^| iex
  pause
  exit /b 1
)
echo Using: %CLI%
echo.
echo === STEP 1: A browser will open. Log in and click Authorize.
echo === STEP 2: Copy the code shown in the browser.
echo === STEP 3: Right-click in this window to paste, then press Enter.
echo.
"%CLI%" auth login --claudeai
echo.
echo === Login status:
"%CLI%" auth status
echo.
pause
