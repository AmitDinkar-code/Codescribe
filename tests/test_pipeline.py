"""Tests for Phase 3/4 — offline generation + Markdown rendering."""

from __future__ import annotations

from pathlib import Path

from codescribe.graph import build_graph, find_cycles
from codescribe.models import ProjectDoc
from codescribe.parser import parse_project
from codescribe.pipeline import build_payload, generate
from codescribe.render import render_markdown

SAMPLE = Path(__file__).resolve().parent.parent / "sample_repo"


def _doc() -> ProjectDoc:
    modules = parse_project(SAMPLE)
    cycles = find_cycles(build_graph(modules))
    payload = build_payload(modules, cycles)
    doc, mode = generate(payload, use_llm=False)
    assert mode == "offline"
    return doc


def test_offline_doc_is_schema_valid() -> None:
    doc = _doc()
    assert isinstance(doc, ProjectDoc)
    assert doc.modules
    assert doc.dependency_cycles  # sample repo has a cycle
    # The high-severity 2-node cycle should be flagged high.
    assert any(c.severity == "high" for c in doc.dependency_cycles)


def test_render_produces_markdown() -> None:
    md = render_markdown(_doc())
    assert md.startswith("#")
    assert "Dependency Cycle Warnings" in md
    assert "Module Reference" in md
    # Function signatures from the sample should surface.
    assert "format_currency" in md
