@echo off
REM Windows convenience launcher for codescribe.
REM Usage: codescribe.bat --target .\sample_repo --out README.md --no-llm
REM Runs the package from this script's own directory and forwards all args.

setlocal
cd /d "%~dp0"

REM Prefer the project venv's Python if present, else the py launcher, else python.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m codescribe %*
) else (
    where py >nul 2>nul && (
        py -m codescribe %*
    ) || (
        python -m codescribe %*
    )
)

endlocal
