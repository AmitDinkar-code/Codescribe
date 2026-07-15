@echo off
REM Build and open the offline codescribe showcase.
REM Runs make_showcase.py (which runs codescribe --no-llm on sample_repo and
REM writes a single self-contained showcase.html), then opens it in the browser.
REM No API key, no network, no external assets required.

setlocal
cd /d "%~dp0"

REM Prefer the project venv's Python if present, else the py launcher, else python.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" make_showcase.py
) else (
    where py >nul 2>nul && (
        py make_showcase.py
    ) || (
        python make_showcase.py
    )
)

if exist "showcase.html" (
    start "" "showcase.html"
) else (
    echo Failed to build showcase.html
)

endlocal
