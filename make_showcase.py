#!/usr/bin/env python3
"""Build a single, fully self-contained ``showcase.html`` for codescribe.

This script runs the codescribe pipeline against the bundled ``sample_repo/`` in
deterministic, no-API-key mode (``--no-llm``), then renders a polished, offline
HTML page that presents:

  * a header band with title + one-line subtitle,
  * a short "what this is" blurb,
  * the INPUT  — the sample_repo source files (with snippets),
  * the dependency graph codescribe builds (modules + import edges + cycle),
  * the OUTPUT — the generated Markdown README, rendered to HTML.

Everything is inline (CSS + content). There are NO external URLs, CDNs, fonts,
scripts, or fetch calls — the page works from a file:// URL with no network.

Standard library only. Cross-platform (pathlib, utf-8).

Usage:
    python make_showcase.py
"""

from __future__ import annotations

import html
import math
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLE_REPO = HERE / "sample_repo"
README_OUT = HERE / "sample_README.md"


# --------------------------------------------------------------------------- #
#  Theme tokens (shared dark dashboard palette across our projects)
# --------------------------------------------------------------------------- #
BG = "#0d1117"
PANEL = "#161b22"
BORDER = "#30363d"
TEXT = "#e6edf3"
MUTED = "#8b949e"
ACCENT = "#58a6ff"
GOOD = "#3fb950"
WARN = "#d29922"
BAD = "#f85149"


# --------------------------------------------------------------------------- #
#  Step 1 — run codescribe (deterministic, offline) to produce the README
# --------------------------------------------------------------------------- #
def generate_readme() -> tuple[str, str]:
    """Run codescribe ``--no-llm`` on sample_repo and return (markdown, telemetry).

    Falls back to an already-generated ``sample_README.md`` if the subprocess
    cannot run (e.g. missing jinja2/pydantic), so the showcase can still build.
    """
    telemetry = ""
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "codescribe",
                "--target",
                str(SAMPLE_REPO),
                "--out",
                str(README_OUT),
                "--no-llm",
            ],
            cwd=str(HERE),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        telemetry = (proc.stderr or "").strip()
        if proc.returncode != 0:
            print("[make_showcase] codescribe run failed; falling back to existing README.")
            print(telemetry)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[make_showcase] could not invoke codescribe ({exc}); using existing README.")

    if README_OUT.exists():
        return README_OUT.read_text(encoding="utf-8"), telemetry
    raise SystemExit(
        "error: no README produced and no existing sample_README.md to fall back on."
    )


# --------------------------------------------------------------------------- #
#  Step 2 — extract the dependency graph (modules + edges + cycles)
#  Uses codescribe's OWN parser/graph modules (standard-library only, so this
#  imports cleanly even without jinja2/pydantic installed).
# --------------------------------------------------------------------------- #
def extract_graph() -> dict:
    """Return {'nodes': [...], 'edges': [(src,dst)...], 'cycles': [[...]]}.

    Best-effort: if codescribe's modules can't be imported, returns empty data
    and the showcase simply omits the graph panel.
    """
    try:
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        from codescribe.parser import parse_project
        from codescribe.graph import build_graph, find_cycles

        modules = parse_project(SAMPLE_REPO)
        graph = build_graph(modules)
        cycles = find_cycles(graph)
        nodes = sorted(graph.adjacency.keys())
        edges = graph.edges()
        return {"nodes": nodes, "edges": edges, "cycles": cycles}
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[make_showcase] graph extraction skipped ({exc}).")
        return {"nodes": [], "edges": [], "cycles": []}


# --------------------------------------------------------------------------- #
#  Step 3 — a tiny, dependency-free Markdown -> HTML converter
#  Supports: headings, fenced code blocks, inline code, bold, links (text only),
#  unordered (nested) lists, horizontal rules, and paragraphs.
# --------------------------------------------------------------------------- #
_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_LIST_RE = re.compile(r"^(\s*)[-*]\s+(.*)$")


def _inline(text: str) -> str:
    """Render inline Markdown to safe HTML (no external URLs are emitted)."""
    out = html.escape(text, quote=False)
    # Links: keep only the visible text (drop the URL → stays fully offline).
    out = _LINK_RE.sub(lambda m: m.group(1), out)
    # Inline code.
    out = _CODE_RE.sub(lambda m: f"<code>{m.group(1)}</code>", out)
    # Bold.
    out = _BOLD_RE.sub(lambda m: f"<strong>{m.group(1)}</strong>", out)
    return out


def markdown_to_html(md: str) -> str:
    """Convert a Markdown string to an HTML fragment using only the stdlib."""
    lines = md.replace("\r\n", "\n").split("\n")
    parts: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Fenced code block.
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            i += 1
            buf: list[str] = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1  # skip closing fence
            code = html.escape("\n".join(buf), quote=False)
            lang_attr = f' data-lang="{html.escape(lang)}"' if lang else ""
            parts.append(f'<pre class="code"{lang_attr}><code>{code}</code></pre>')
            continue

        # Blank line.
        if not stripped:
            i += 1
            continue

        # Horizontal rule.
        if stripped in ("---", "***", "___"):
            parts.append("<hr/>")
            i += 1
            continue

        # Heading.
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            parts.append(f"<h{level}>{_inline(m.group(2).strip())}</h{level}>")
            i += 1
            continue

        # List (supports nesting by indentation, 2 spaces per level).
        if _LIST_RE.match(line):
            items: list[tuple[int, str]] = []
            while i < n and _LIST_RE.match(lines[i]):
                lm = _LIST_RE.match(lines[i])
                indent = len(lm.group(1).replace("\t", "  "))
                level = indent // 2
                items.append((level, lm.group(2).strip()))
                i += 1
            parts.append(_render_list(items))
            continue

        # Paragraph: gather consecutive "plain" lines.
        buf = []
        while i < n:
            cur = lines[i]
            cs = cur.strip()
            if (
                not cs
                or cs.startswith("```")
                or cs in ("---", "***", "___")
                or _HEADING_RE.match(cur)
                or _LIST_RE.match(cur)
            ):
                break
            buf.append(cs)
            i += 1
        parts.append(f"<p>{_inline(' '.join(buf))}</p>")

    return "\n".join(parts)


def _render_list(items: list[tuple[int, str]]) -> str:
    """Render (level, text) pairs into nested <ul> markup."""
    out: list[str] = []
    stack: list[int] = []  # active open levels
    for level, text in items:
        while stack and stack[-1] > level:
            out.append("</li></ul>")
            stack.pop()
        if stack and stack[-1] == level:
            out.append("</li>")
        if not stack or stack[-1] < level:
            out.append("<ul>")
            stack.append(level)
        out.append(f"<li>{_inline(text)}")
    while stack:
        out.append("</li></ul>")
        stack.pop()
    return "".join(out)


# --------------------------------------------------------------------------- #
#  Step 4 — dependency-graph SVG (inline, no external assets)
# --------------------------------------------------------------------------- #
def graph_svg(graph: dict) -> str:
    """Build an inline SVG of the module dependency graph."""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    cycles = graph.get("cycles", [])
    if not nodes:
        return ""

    # Edges that belong to a detected cycle (rendered in the "bad" colour).
    cycle_edges: set[tuple[str, str]] = set()
    for cyc in cycles:
        for a, b in zip(cyc, cyc[1:]):
            cycle_edges.add((a, b))

    width, height = 640, 420
    cx, cy = width / 2, height / 2
    radius = 150
    r_node = 30

    pos: dict[str, tuple[float, float]] = {}
    count = len(nodes)
    for idx, name in enumerate(nodes):
        angle = -math.pi / 2 + (2 * math.pi * idx / count)
        pos[name] = (cx + radius * math.cos(angle), cy + radius * math.sin(angle))

    svg: list[str] = []
    svg.append(
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="Module dependency graph">'
    )
    # Arrow markers.
    svg.append(
        f'<defs>'
        f'<marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="3" '
        f'orient="auto" markerUnits="strokeWidth">'
        f'<path d="M0,0 L8,3 L0,6 Z" fill="{MUTED}"/></marker>'
        f'<marker id="arrowbad" markerWidth="9" markerHeight="9" refX="8" refY="3" '
        f'orient="auto" markerUnits="strokeWidth">'
        f'<path d="M0,0 L8,3 L0,6 Z" fill="{BAD}"/></marker>'
        f'</defs>'
    )

    # Edges (drawn first, behind the nodes), shortened to node borders.
    for src, dst in edges:
        x1, y1 = pos[src]
        x2, y2 = pos[dst]
        dx, dy = x2 - x1, y2 - y1
        dist = math.hypot(dx, dy) or 1.0
        ux, uy = dx / dist, dy / dist
        sx, sy = x1 + ux * r_node, y1 + uy * r_node
        ex, ey = x2 - ux * (r_node + 6), y2 - uy * (r_node + 6)
        bad = (src, dst) in cycle_edges
        color = BAD if bad else MUTED
        marker = "arrowbad" if bad else "arrow"
        sw = "2.4" if bad else "1.5"
        svg.append(
            f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" '
            f'stroke="{color}" stroke-width="{sw}" marker-end="url(#{marker})"/>'
        )

    # Nodes.
    cycle_nodes = {m for cyc in cycles for m in cyc}
    for name in nodes:
        x, y = pos[name]
        in_cycle = name in cycle_nodes
        stroke = BAD if in_cycle else ACCENT
        fill = "#21262d"
        label = name if len(name) <= 12 else name[:11] + "…"
        svg.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r_node}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="2"/>'
        )
        svg.append(
            f'<text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle" '
            f'font-family="ui-monospace,Menlo,Consolas,monospace" font-size="12" '
            f'fill="{TEXT}">{html.escape(label)}</text>'
        )
    svg.append("</svg>")
    return "".join(svg)


# --------------------------------------------------------------------------- #
#  Step 5 — assemble the page
# --------------------------------------------------------------------------- #
def source_files() -> list[tuple[str, str]]:
    """Return (relative_name, source_text) for every .py file in sample_repo."""
    out: list[tuple[str, str]] = []
    for path in sorted(SAMPLE_REPO.rglob("*.py")):
        rel = path.relative_to(SAMPLE_REPO).as_posix()
        out.append((rel, path.read_text(encoding="utf-8")))
    return out


def build_html(readme_md: str, telemetry: str, graph: dict) -> str:
    files = source_files()
    readme_html = markdown_to_html(readme_md)
    svg = graph_svg(graph)

    # Input file cards.
    input_cards: list[str] = []
    for name, src in files:
        loc = src.count("\n") + 1
        input_cards.append(
            f'<div class="filecard">'
            f'<div class="filehead"><span class="fname">{html.escape(name)}</span>'
            f'<span class="badge">{loc} lines</span></div>'
            f'<pre class="code"><code>{html.escape(src, quote=False)}</code></pre>'
            f"</div>"
        )

    # Graph legend + telemetry stats.
    n_nodes = len(graph.get("nodes", []))
    n_edges = len(graph.get("edges", []))
    n_cycles = len(graph.get("cycles", []))
    cycle_labels = [" → ".join(c) for c in graph.get("cycles", [])]

    graph_panel = ""
    if svg:
        cyc_html = ""
        if cycle_labels:
            cyc_html = (
                '<div class="cyclebox"><span class="badge bad">CYCLE</span> '
                + " ".join(f"<code>{html.escape(c)}</code>" for c in cycle_labels)
                + "</div>"
            )
        graph_panel = f"""
      <section class="panel">
        <h2 class="panel-title">Dependency graph <span class="muted">(graph.py)</span></h2>
        <p class="muted small">Directed import graph over the sample's modules. A DFS with a
        recursion stack flags cyclic imports; the red edges/nodes are the detected cycle.</p>
        <div class="stats">
          <div class="stat"><span class="num" style="color:{ACCENT}">{n_nodes}</span><span class="lbl">modules</span></div>
          <div class="stat"><span class="num" style="color:{TEXT}">{n_edges}</span><span class="lbl">import edges</span></div>
          <div class="stat"><span class="num" style="color:{BAD}">{n_cycles}</span><span class="lbl">cycles</span></div>
        </div>
        <div class="graphwrap">{svg}</div>
        {cyc_html}
      </section>"""

    telemetry_html = ""
    if telemetry:
        telemetry_html = (
            '<div class="telemetry"><span class="badge good">codescribe log</span>'
            f"<pre class=\"code small\"><code>{html.escape(telemetry, quote=False)}</code></pre></div>"
        )

    css = f"""
    :root {{ color-scheme: dark; }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; background: {BG}; color: {TEXT};
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.55;
    }}
    a {{ color: {ACCENT}; }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      background: #1f2630; padding: .12em .38em; border-radius: 5px;
      font-size: .88em; color: #cdd9e5;
    }}
    pre.code {{
      background: #0b0f14; border: 1px solid {BORDER}; border-radius: 8px;
      padding: 14px 16px; overflow-x: auto; margin: 10px 0 0;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12.5px; line-height: 1.5; color: #cdd9e5;
    }}
    pre.code code {{ background: none; padding: 0; font-size: inherit; color: inherit; }}
    pre.code.small {{ font-size: 11.5px; }}
    .header {{
      background: linear-gradient(180deg, #161b22 0%, #0d1117 100%);
      border-bottom: 1px solid {BORDER}; padding: 30px 40px;
    }}
    .header h1 {{ margin: 0; font-size: 30px; letter-spacing: -.5px; }}
    .header h1 .dot {{ color: {ACCENT}; }}
    .header .sub {{ margin: 8px 0 0; color: {MUTED}; font-size: 15px; }}
    .pipeline {{ margin-top: 16px; display: flex; flex-wrap: wrap; gap: 8px; }}
    .pill {{
      border: 1px solid {BORDER}; background: {PANEL}; color: {MUTED};
      padding: 5px 12px; border-radius: 20px; font-size: 12.5px;
    }}
    .pill b {{ color: {TEXT}; font-weight: 600; }}
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 28px 40px 60px; }}
    .blurb {{
      background: {PANEL}; border: 1px solid {BORDER}; border-left: 3px solid {ACCENT};
      border-radius: 8px; padding: 16px 20px; margin: 0 0 26px; color: #c9d4e0;
    }}
    .blurb b {{ color: {TEXT}; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 22px; align-items: start; }}
    @media (max-width: 980px) {{ .grid {{ grid-template-columns: 1fr; }} }}
    .panel {{
      background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px;
      padding: 20px 22px; margin-bottom: 22px;
    }}
    .panel-title {{ margin: 0 0 14px; font-size: 17px; display: flex; align-items: baseline; gap: 8px; }}
    .col-label {{
      display: inline-block; font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase;
      color: {MUTED}; margin-bottom: 10px; font-weight: 600;
    }}
    .filecard {{ margin-bottom: 16px; }}
    .filehead {{ display: flex; align-items: center; justify-content: space-between; }}
    .fname {{ font-family: ui-monospace, Menlo, Consolas, monospace; color: {ACCENT}; font-size: 13.5px; }}
    .badge {{
      font-size: 10.5px; letter-spacing: .5px; padding: 2px 8px; border-radius: 10px;
      border: 1px solid {BORDER}; color: {MUTED}; background: #0b0f14; white-space: nowrap;
    }}
    .badge.good {{ color: {GOOD}; border-color: #1c3a26; }}
    .badge.bad {{ color: {BAD}; border-color: #43222a; }}
    .stats {{ display: flex; gap: 26px; margin: 4px 0 14px; }}
    .stat {{ display: flex; flex-direction: column; }}
    .stat .num {{ font-size: 26px; font-weight: 700; line-height: 1; }}
    .stat .lbl {{ font-size: 11.5px; color: {MUTED}; margin-top: 4px; }}
    .graphwrap {{
      background: #0b0f14; border: 1px solid {BORDER}; border-radius: 8px; padding: 8px;
    }}
    .cyclebox {{ margin-top: 12px; font-size: 13px; color: {MUTED}; }}
    .cyclebox code {{ color: {BAD}; }}
    .telemetry {{ margin-top: 16px; }}
    .muted {{ color: {MUTED}; }}
    .small {{ font-size: 12.5px; }}
    /* Rendered README */
    .readme h1 {{ font-size: 24px; border-bottom: 1px solid {BORDER}; padding-bottom: 8px; margin: 22px 0 14px; }}
    .readme h2 {{ font-size: 19px; border-bottom: 1px solid {BORDER}; padding-bottom: 6px; margin: 26px 0 12px; }}
    .readme h3 {{ font-size: 16px; margin: 20px 0 8px; }}
    .readme h4 {{ font-size: 14px; color: {MUTED}; text-transform: uppercase; letter-spacing: .5px; margin: 16px 0 6px; }}
    .readme p {{ margin: 8px 0; }}
    .readme ul {{ margin: 8px 0; padding-left: 22px; }}
    .readme li {{ margin: 4px 0; }}
    .readme hr {{ border: none; border-top: 1px solid {BORDER}; margin: 24px 0; }}
    .readme h2:first-child, .readme h1:first-child {{ margin-top: 0; }}
    .footer {{ text-align: center; color: {MUTED}; font-size: 12.5px; margin-top: 36px; }}
    """

    pipeline_pills = (
        '<span class="pill"><b>1</b> AST extract</span>'
        '<span class="pill"><b>2</b> dependency graph</span>'
        '<span class="pill"><b>3</b> schema-validated docs <i>(offline)</i></span>'
        '<span class="pill"><b>4</b> Markdown render</span>'
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>codescribe — showcase</title>
<style>{css}</style>
</head>
<body>
  <header class="header">
    <h1>codescribe<span class="dot">.</span></h1>
    <p class="sub">Reads a Python codebase <b>without executing it</b>, maps how modules depend on
    each other, flags cyclic imports, and renders a clean README — here, fully offline (<code>--no-llm</code>).</p>
    <div class="pipeline">{pipeline_pills}</div>
  </header>

  <main class="wrap">
    <div class="blurb">
      <b>What this is.</b> A static demo of the codescribe CLI. It was run against the bundled
      <code>sample_repo/</code> in deterministic, no-API-key mode. The left column is the <b>input</b>
      (the actual source files); the right column is the <b>output</b> (the generated README). In the
      middle is the dependency graph codescribe builds internally — including the intentional
      <code>order ↔ customer</code> import cycle it detects.
    </div>

    {graph_panel}

    <div class="grid">
      <section class="panel">
        <span class="col-label">Input → sample_repo/</span>
        <h2 class="panel-title">Source files <span class="muted">({len(files)} modules)</span></h2>
        {''.join(input_cards)}
      </section>

      <section class="panel">
        <span class="col-label">Output → generated README</span>
        <h2 class="panel-title">codescribe README <span class="muted">(--no-llm)</span></h2>
        {telemetry_html}
        <div class="readme">{readme_html}</div>
      </section>
    </div>

    <p class="footer">Generated offline by <code>make_showcase.py</code> — no API keys, no network, no external assets.</p>
  </main>
</body>
</html>
"""


def main() -> int:
    readme_md, telemetry = generate_readme()
    graph = extract_graph()
    page = build_html(readme_md, telemetry, graph)
    out = HERE / "showcase.html"
    out.write_text(page, encoding="utf-8")
    print(f"[make_showcase] wrote {out}")
    print(f"[make_showcase] {len(page):,} bytes, "
          f"{len(graph.get('nodes', []))} graph nodes, "
          f"{len(graph.get('edges', []))} edges, "
          f"{len(graph.get('cycles', []))} cycle(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
