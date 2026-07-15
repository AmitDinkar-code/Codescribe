# Windows conversion notes

This folder is the **Windows build** of `codescribe`. The application logic is
unchanged — the parser, dependency graph, LLM pipeline, and renderer are byte-for-byte
identical to the macOS/Linux version. The original code was already written to be
cross-platform (it uses `pathlib` for all path handling and passes
`encoding="utf-8"` explicitly on every file read/write), so only a few
Windows-specific touches were needed.

## What changed vs. the macOS build

1. **UTF-8 console guard (`codescribe/cli.py`).**
   The generated Markdown contains non-ASCII characters (`⚠️` in the cycle
   warning heading, `→` in the cycle path and footer). When you run without
   `--out` and the Markdown is printed to the terminal, the legacy Windows
   console code page (cp1252) raises `UnicodeEncodeError`. `main()` now calls
   `_force_utf8_console()`, which reconfigures `stdout`/`stderr` to UTF-8. It is a
   harmless no-op on macOS/Linux (already UTF-8), so the same code runs everywhere.

2. **`codescribe.bat` launcher (new).**
   A double-clickable / command-line launcher that `cd`s into the project, prefers
   the project `.venv` Python, and falls back to the `py` launcher or `python`.
   Equivalent to `py -m codescribe ...`.

3. **`README.md` rewritten for Windows.**
   Commands use `py` / `python`, `set` / `setx` / `$env:` for the API key,
   `.venv\Scripts\activate` (and the PowerShell `Activate.ps1` note), and
   backslash path examples.

4. **`.gitignore` extended.**
   Added Windows artifacts (`Thumbs.db`, `Desktop.ini`, `*.pyd`, `*.lnk`,
   `$RECYCLE.BIN/`) and common editor folders.

## What did NOT need to change (and why)

- **Path handling** — all paths go through `pathlib.Path`, which produces correct
  Windows paths automatically. Module/rel-path strings are rendered with
  `.as_posix()` deliberately (forward slashes read cleanly in the generated
  Markdown on every OS); these are display strings, not filesystem operations.
- **File encoding** — every `read_text` / `write_text` already passes
  `encoding="utf-8"`, so the default Windows cp1252 encoding is never used for
  source files or output.
- **Directory crawling, cycle detection, Jinja2 rendering, Pydantic schemas, the
  Anthropic SDK call** — all platform-independent.

## Quick verify on Windows

```bat
py -m venv .venv
.venv\Scripts\activate
pip install -e .
py -m pytest -q
py -m codescribe --target .\sample_repo --out sample_README.md --no-llm
type sample_README.md
```
