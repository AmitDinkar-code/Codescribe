"""codescribe — deterministic Python codebase documentation generator.

Pipeline:
  1. parser  — AST extraction of functions, classes, imports, docstrings
  2. graph   — module dependency graph + DFS cyclic-dependency detection
  3. pipeline — schema-validated (Pydantic) LLM documentation, with offline mode
  4. render  — Jinja2 Markdown README generation
"""

from __future__ import annotations

from .graph import build_graph, find_cycles, topological_order
from .models import ProjectDoc
from .parser import parse_project
from .pipeline import build_payload, generate
from .render import render_markdown

__version__ = "0.1.0"

__all__ = [
    "parse_project",
    "build_graph",
    "find_cycles",
    "topological_order",
    "build_payload",
    "generate",
    "render_markdown",
    "ProjectDoc",
    "__version__",
]
