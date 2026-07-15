"""Tests for Phase 2 — dependency graph + cycle detection."""

from __future__ import annotations

from pathlib import Path

from codescribe.graph import build_graph, find_cycles, topological_order
from codescribe.parser import parse_project

SAMPLE = Path(__file__).resolve().parent.parent / "sample_repo"


def test_detects_known_cycle() -> None:
    modules = parse_project(SAMPLE)
    graph = build_graph(modules)
    cycles = find_cycles(graph)

    assert cycles, "expected at least one cycle in sample_repo"
    # Module names are relative to the crawl root (sample_repo/), so the cycle
    # members are 'order' and 'customer'.
    members = {frozenset(c[:-1]) for c in cycles}
    assert frozenset({"order", "customer"}) in members


def test_cycle_makes_topological_order_none() -> None:
    modules = parse_project(SAMPLE)
    graph = build_graph(modules)
    assert topological_order(graph) is None


def test_acyclic_graph_orders_leaves_first(tmp_path: Path) -> None:
    (tmp_path / "leaf.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "mid.py").write_text("import leaf\n", encoding="utf-8")
    (tmp_path / "top.py").write_text("import mid\n", encoding="utf-8")

    modules = parse_project(tmp_path)
    graph = build_graph(modules)
    assert find_cycles(graph) == []

    order = topological_order(graph)
    assert order is not None
    assert order.index("leaf") < order.index("mid") < order.index("top")


def test_relative_import_resolution(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "a.py").write_text("from . import b\n", encoding="utf-8")
    (pkg / "b.py").write_text("x = 1\n", encoding="utf-8")

    modules = parse_project(tmp_path)
    graph = build_graph(modules)
    assert "pkg.b" in graph.adjacency["pkg.a"]
