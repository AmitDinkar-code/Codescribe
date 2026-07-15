"""Phase 4 — CLI integration.

Wires the whole pipeline together so a user can run:

    python -m codescribe --target ./my_repo --out README.md

Flow: crawl + AST extraction (Phase 1) → dependency graph + cycle detection
(Phase 2) → schema-validated LLM documentation (Phase 3) → Markdown render
(Phase 4).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .graph import build_graph, find_cycles
from .parser import parse_project
from .pipeline import DEFAULT_MODEL, build_payload, generate


def _force_utf8_console() -> None:
    """Ensure stdout/stderr can emit non-ASCII (e.g. the ``⚠️`` and ``→`` in the
    rendered Markdown).

    On Windows the console defaults to a legacy code page (cp1252), so writing
    those characters to stdout raises ``UnicodeEncodeError``. Reconfiguring to
    UTF-8 fixes it. This is a no-op (and harmless) on macOS/Linux, which already
    default to UTF-8.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass
from .render import render_markdown


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codescribe",
        description=(
            "Generate a README for a Python codebase via AST extraction, "
            "dependency-cycle detection, and a schema-validated LLM pipeline."
        ),
    )
    parser.add_argument(
        "--target",
        "-t",
        type=Path,
        required=True,
        help="Path to the Python file or directory to document.",
    )
    parser.add_argument(
        "--out",
        "-o",
        type=Path,
        default=None,
        help="Output Markdown file. Defaults to stdout.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Anthropic model id (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip the LLM and build documentation deterministically from telemetry.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Anthropic API key (otherwise uses ANTHROPIC_API_KEY / ant profile).",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    target: Path = args.target
    if not target.exists():
        print(f"error: target not found: {target}", file=sys.stderr)
        return 2

    # Phase 1 — parse.
    modules = parse_project(target)
    if not modules:
        print(f"error: no parseable Python files under {target}", file=sys.stderr)
        return 1
    print(f"[codescribe] parsed {len(modules)} module(s).", file=sys.stderr)

    # Phase 2 — graph + cycles.
    graph = build_graph(modules)
    cycles = find_cycles(graph)
    print(
        f"[codescribe] {len(graph.edges())} internal import edge(s), "
        f"{len(cycles)} cycle(s) detected.",
        file=sys.stderr,
    )

    # Phase 3 — structured documentation.
    name_hint = target.resolve().name if target.is_dir() else target.resolve().stem
    payload = build_payload(modules, cycles, name_hint=name_hint)
    doc, mode = generate(
        payload,
        use_llm=not args.no_llm,
        model=args.model,
        api_key=args.api_key,
    )
    print(f"[codescribe] documentation generated ({mode}).", file=sys.stderr)

    # Phase 4 — render.
    markdown = render_markdown(doc)
    if args.out:
        args.out.write_text(markdown, encoding="utf-8")
        print(f"[codescribe] wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(markdown)
    return 0


def main(argv: list[str] | None = None) -> int:
    _force_utf8_console()
    args = build_arg_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
