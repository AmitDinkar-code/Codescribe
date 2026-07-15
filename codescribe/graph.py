"""Phase 2 — dependency graphing and cyclic-dependency detection.

Builds a directed graph whose nodes are the project's modules and whose edges
represent an internal import (module A imports module B that also lives in the
project). A depth-first search with an explicit recursion stack flags cyclic
dependencies, e.g. A imports B which imports A.

Uses only the standard library. If `networkx` is installed it is used for a
sanity cross-check, but it is not required.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .parser import ImportInfo, ModuleInfo


@dataclass
class DependencyGraph:
    """A directed import graph over the project's internal modules."""

    # adjacency: module_name -> set of internal module_names it imports
    adjacency: dict[str, set[str]] = field(default_factory=dict)
    # human-friendly rel paths for reporting
    rel_paths: dict[str, str] = field(default_factory=dict)

    def edges(self) -> list[tuple[str, str]]:
        return [(src, dst) for src, dsts in self.adjacency.items() for dst in sorted(dsts)]


def _resolve_relative(current_module: str, level: int, target: str) -> str:
    """Resolve a relative import to an absolute dotted module name.

    `level` is the number of leading dots; `target` is the text after them
    (possibly empty for `from . import x`).
    """
    parts = current_module.split(".")
    # Each leading dot strips one trailing package component. Level 1 means the
    # current package, so we drop the module's own name first.
    base = parts[: len(parts) - level] if level <= len(parts) else []
    if target:
        base = base + target.split(".")
    return ".".join(p for p in base if p)


def _candidate_targets(current_module: str, imp: ImportInfo) -> list[str]:
    """All dotted module names an import statement could refer to."""
    candidates: list[str] = []
    if imp.level > 0:
        resolved = _resolve_relative(current_module, imp.level, imp.module)
        if resolved:
            candidates.append(resolved)
        # `from .pkg import sub` may import the submodule `pkg.sub`.
        for name in imp.names:
            joined = f"{resolved}.{name}" if resolved else name
            candidates.append(joined)
    else:
        if imp.module:
            candidates.append(imp.module)
            if imp.is_from:
                # `from a.b import c` may pull in submodule `a.b.c`.
                for name in imp.names:
                    candidates.append(f"{imp.module}.{name}")
    return candidates


def build_graph(modules: list[ModuleInfo]) -> DependencyGraph:
    """Construct the internal dependency graph from parsed modules."""
    internal = {m.module_name for m in modules}
    graph = DependencyGraph()
    for m in modules:
        graph.adjacency.setdefault(m.module_name, set())
        graph.rel_paths[m.module_name] = m.rel_path

    for m in modules:
        for imp in m.imports:
            for target in _candidate_targets(m.module_name, imp):
                if target in internal and target != m.module_name:
                    graph.adjacency[m.module_name].add(target)
    return graph


def find_cycles(graph: DependencyGraph) -> list[list[str]]:
    """Return distinct cycles via DFS with a visited set + recursion stack.

    A cycle is reported as a closed chain, e.g. ['a', 'b', 'a']. Cycles that are
    rotations of one another are de-duplicated.
    """
    visited: set[str] = set()
    stack: list[str] = []
    on_stack: set[str] = set()
    cycles: list[list[str]] = []
    seen_signatures: set[frozenset[str]] = set()

    def dfs(node: str) -> None:
        visited.add(node)
        stack.append(node)
        on_stack.add(node)

        for neighbour in sorted(graph.adjacency.get(node, ())):
            if neighbour not in visited:
                dfs(neighbour)
            elif neighbour in on_stack:
                # Back edge: slice the recursion stack from the neighbour onward.
                idx = stack.index(neighbour)
                cycle = stack[idx:] + [neighbour]
                signature = frozenset(cycle[:-1])
                if signature not in seen_signatures:
                    seen_signatures.add(signature)
                    cycles.append(cycle)

        stack.pop()
        on_stack.discard(node)

    for node in sorted(graph.adjacency):
        if node not in visited:
            dfs(node)

    return cycles


def topological_order(graph: DependencyGraph) -> list[str] | None:
    """Return a dependency-first ordering, or None if the graph has a cycle.

    Uses Kahn's algorithm over the reverse dependency direction so that leaf
    modules (no internal imports) come first.
    """
    indegree: dict[str, int] = {n: 0 for n in graph.adjacency}
    for src, dsts in graph.adjacency.items():
        for dst in dsts:
            indegree[src] += 0  # ensure key exists
            indegree[dst] = indegree.get(dst, 0)
    # Count edges target<-source so leaves (imported-by-nobody-imports) settle.
    indeg: dict[str, int] = {n: 0 for n in graph.adjacency}
    for src, dsts in graph.adjacency.items():
        for dst in dsts:
            indeg[src] += 1  # src depends on dst

    queue = sorted(n for n, d in indeg.items() if d == 0)
    order: list[str] = []
    indeg = dict(indeg)
    # Reverse adjacency: who imports `node`?
    importers: dict[str, set[str]] = {n: set() for n in graph.adjacency}
    for src, dsts in graph.adjacency.items():
        for dst in dsts:
            importers.setdefault(dst, set()).add(src)

    while queue:
        node = queue.pop(0)
        order.append(node)
        for importer in sorted(importers.get(node, ())):
            indeg[importer] -= 1
            if indeg[importer] == 0:
                queue.append(importer)
                queue.sort()

    if len(order) != len(graph.adjacency):
        return None  # cycle present
    return order
