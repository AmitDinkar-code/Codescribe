# codescribe (Windows)

**Deterministic AST extraction → dependency-graph analysis → schema-validated LLM documentation → Markdown README**, wrapped in a CLI.

`codescribe` reads a Python codebase *without executing it*, maps how its modules
depend on one another, flags cyclic dependencies, asks Claude to turn that
telemetry into developer documentation under a strict Pydantic schema, and
renders the result as a clean README.

> This is the **Windows** build of the project. The logic is identical to the
> macOS/Linux version; only the run commands and a console-encoding guard differ.
> See `WINDOWS.md` for the exact list of changes.

## Why it's built this way

The four phases map directly onto four engineering milestones:

| Phase | Module | What it does |
|------|--------|--------------|
| **1 — Parsing engine** | `parser.py` | Walks a directory, parses every `.py` file into an AST (`ast`, `pathlib`), and extracts functions, arguments, return types, classes, imports, docstrings, and internal calls — **never executing the code**. |
| **2 — Dependency graph** | `graph.py` | Builds a directed import graph over the project's modules and runs a DFS with a visited set + recursion stack to flag **cyclic dependencies** (A imports B imports A). |
| **3 — AI pipeline** | `pipeline.py` + `models.py` | Feeds the telemetry + cycle paths to Claude and forces the response to satisfy strict **Pydantic** schemas via the Anthropic SDK's structured output (`messages.parse`). Includes a deterministic offline fallback. |
| **4 — Markdown + CLI** | `render.py`, `templates/`, `cli.py` | Renders the validated objects into Markdown with **Jinja2** and exposes the whole pipeline through an `argparse` CLI. |

## Requirements

- **Python 3.10+** for Windows from [python.org](https://www.python.org/downloads/windows/).
  During install, tick **"Add python.exe to PATH"** (or use the bundled `py` launcher).

## Install (PowerShell or Command Prompt)

```bat
cd codescribe

:: create and activate a virtual environment
py -m venv .venv
.venv\Scripts\activate

:: install
pip install -e .
:: or, just the runtime deps:
pip install -r requirements.txt
```

In **PowerShell**, activation is `.venv\Scripts\Activate.ps1` instead. If PowerShell
blocks the script, run once:
`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`.

Runtime dependencies: `pydantic`, `jinja2`, `anthropic`. `networkx` is optional.

## Use

```bat
:: Full pipeline (uses Claude — needs credentials, see below)
py -m codescribe --target .\my_repo --out README.md

:: Deterministic, no API key required (docs built from your docstrings)
py -m codescribe --target .\my_repo --out README.md --no-llm

:: Print to stdout instead of a file
py -m codescribe --target .\my_repo --no-llm
```

After `pip install -e .` the `codescribe` console script (`codescribe.exe`) is on
your PATH inside the venv:

```bat
codescribe --target .\my_repo --out README.md
```

There's also a convenience launcher in the project root:

```bat
codescribe.bat --target .\sample_repo --out sample_README.md --no-llm
```

### Options

| Flag | Description |
|------|-------------|
| `--target`, `-t` | File or directory to document (required). |
| `--out`, `-o` | Output Markdown file (defaults to stdout). |
| `--model` | Anthropic model id (default `claude-opus-4-8`). |
| `--no-llm` | Skip Claude; build docs deterministically from telemetry. |
| `--api-key` | Anthropic API key (otherwise `ANTHROPIC_API_KEY` / `ant` profile). |

### Credentials (for the LLM path)

Set the API key for the current session:

```bat
:: Command Prompt
set ANTHROPIC_API_KEY=sk-ant-...

:: PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-..."

:: persist it across sessions (Command Prompt)
setx ANTHROPIC_API_KEY "sk-ant-..."
```

If credentials are missing or the `anthropic` package isn't installed,
`codescribe` prints the reason and falls back to `--no-llm` output, so it never
hard-fails.

## Demo

The repo ships a `sample_repo\` with a deliberate `order ↔ customer` import
cycle:

```bat
py -m codescribe --target .\sample_repo --out sample_README.md --no-llm
```

The generated `sample_README.md` flags the cycle as **HIGH** severity with a
suggested fix, and documents every module, class, and function from the code's
own docstrings.

## Showcase

For a quick, no-setup look at what `codescribe` produces, build the offline
showcase page. It runs the deterministic `--no-llm` pipeline against
`sample_repo\` and writes a single self-contained `showcase.html` (inline CSS,
no network, no API key, no external assets):

```bat
showcase.bat
```

Or run the generator directly:

```bat
py make_showcase.py
:: then open showcase.html in any browser
```

The page shows the **input** source files, the internal **dependency graph**
(with the intentional `order ↔ customer` cycle highlighted), and the generated
README rendered as HTML — all in one file you can double-click on Windows.

## Tests

```bat
pip install pytest
py -m pytest -q
```

## Layout

```
codescribe\
├── codescribe\
│   ├── parser.py        # Phase 1 — AST extraction
│   ├── graph.py         # Phase 2 — dependency graph + cycle detection
│   ├── models.py        # Phase 3 — Pydantic output schemas
│   ├── pipeline.py      # Phase 3 — LLM + structured output (+ offline fallback)
│   ├── render.py        # Phase 4 — Jinja2 Markdown rendering
│   ├── cli.py           # Phase 4 — CLI (with Windows UTF-8 console guard)
│   └── templates\readme.md.j2
├── sample_repo\         # demo project with an intentional import cycle
├── tests\
├── codescribe.bat       # Windows convenience launcher
├── WINDOWS.md           # what changed from the macOS build
├── pyproject.toml
└── requirements.txt
```
