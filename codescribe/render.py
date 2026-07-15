"""Phase 4 — Markdown generation.

Renders a validated `ProjectDoc` into a clean README using a Jinja2 template.
"""

from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .models import ProjectDoc

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(enabled_extensions=(), default=False),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render_markdown(doc: ProjectDoc) -> str:
    """Render the ProjectDoc to a Markdown string."""
    template = _environment().get_template("readme.md.j2")
    output = template.render(doc=doc)
    # Collapse runs of 3+ blank lines that templating can introduce.
    return re.sub(r"\n{3,}", "\n\n", output).strip() + "\n"
