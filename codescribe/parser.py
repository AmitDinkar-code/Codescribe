"""Phase 1 — the parsing engine.

Reads Python source *without executing it* and extracts structural telemetry
using the standard library `ast` module: module docstrings, imports, function
definitions (args, return types, internal calls, docstrings) and class
definitions. Everything is stored in plain dataclasses so it can be serialised
to JSON for the LLM and consumed by the dependency-graph builder.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

# Directories we never want to crawl into.
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".env",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    "build",
    "dist",
    ".eggs",
}


@dataclass
class ImportInfo:
    """A single import statement, normalised."""

    module: str  # the module being imported, e.g. "os.path" or "pkg.mod"
    names: list[str] = field(default_factory=list)  # imported names, for `from x import a, b`
    level: int = 0  # relative-import dot count (0 = absolute)
    is_from: bool = False  # True for `from ... import ...`


@dataclass
class FunctionInfo:
    name: str
    args: list[str]
    returns: str | None
    docstring: str | None
    decorators: list[str]
    calls: list[str]  # names of functions/methods called inside the body
    lineno: int
    is_async: bool = False

    @property
    def signature(self) -> str:
        prefix = "async def" if self.is_async else "def"
        ret = f" -> {self.returns}" if self.returns else ""
        return f"{prefix} {self.name}({', '.join(self.args)}){ret}"


@dataclass
class ClassInfo:
    name: str
    bases: list[str]
    docstring: str | None
    methods: list[FunctionInfo]
    decorators: list[str]
    lineno: int


@dataclass
class ModuleInfo:
    """All telemetry extracted from one .py file."""

    path: Path  # absolute path on disk
    rel_path: str  # path relative to the crawl root, POSIX style
    module_name: str  # dotted module name, e.g. "pkg.mod"
    docstring: str | None
    imports: list[ImportInfo]
    functions: list[FunctionInfo]  # module-level functions only
    classes: list[ClassInfo]

    def to_telemetry(self) -> dict:
        """A compact JSON-serialisable view for the LLM."""
        return {
            "module": self.module_name,
            "path": self.rel_path,
            "docstring": self.docstring,
            "imports": [
                {
                    "module": imp.module,
                    "names": imp.names,
                    "relative": imp.level > 0,
                }
                for imp in self.imports
            ],
            "functions": [
                {
                    "name": fn.name,
                    "signature": fn.signature,
                    "docstring": fn.docstring,
                    "decorators": fn.decorators,
                    "calls": sorted(set(fn.calls)),
                }
                for fn in self.functions
            ],
            "classes": [
                {
                    "name": cls.name,
                    "bases": cls.bases,
                    "docstring": cls.docstring,
                    "methods": [
                        {
                            "name": m.name,
                            "signature": m.signature,
                            "docstring": m.docstring,
                        }
                        for m in cls.methods
                    ],
                }
                for cls in self.classes
            ],
        }


def _name_of(node: ast.AST) -> str:
    """Best-effort dotted/string rendering of an expression node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _name_of(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _name_of(node.func)
    if isinstance(node, ast.Subscript):
        return _name_of(node.value)
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _annotation(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _format_args(args: ast.arguments) -> list[str]:
    """Render a function's arguments as a list of 'name: type = default' strings."""
    rendered: list[str] = []

    posonly = getattr(args, "posonlyargs", [])
    regular = posonly + args.args
    # Defaults align to the tail of posonly+args.
    defaults = list(args.defaults)
    pad = [None] * (len(regular) - len(defaults))
    arg_defaults = pad + defaults

    for arg, default in zip(regular, arg_defaults):
        rendered.append(_render_arg(arg, default))
        if posonly and arg is posonly[-1]:
            rendered.append("/")

    if args.vararg:
        rendered.append("*" + _render_arg(args.vararg, None))
    elif args.kwonlyargs:
        rendered.append("*")

    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        rendered.append(_render_arg(arg, default))

    if args.kwarg:
        rendered.append("**" + _render_arg(args.kwarg, None))

    return rendered


def _render_arg(arg: ast.arg, default: ast.AST | None) -> str:
    out = arg.arg
    ann = _annotation(arg.annotation)
    if ann:
        out += f": {ann}"
    if default is not None:
        try:
            out += f" = {ast.unparse(default)}"
        except Exception:
            out += " = ..."
    return out


class _CallCollector(ast.NodeVisitor):
    """Collects the names of all calls made within a function body."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 (ast API)
        name = _name_of(node.func)
        if name:
            self.calls.append(name)
        self.generic_visit(node)


def _build_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionInfo:
    collector = _CallCollector()
    for child in node.body:
        collector.visit(child)
    return FunctionInfo(
        name=node.name,
        args=_format_args(node.args),
        returns=_annotation(node.returns),
        docstring=ast.get_docstring(node),
        decorators=[_name_of(d) for d in node.decorator_list],
        calls=collector.calls,
        lineno=node.lineno,
        is_async=isinstance(node, ast.AsyncFunctionDef),
    )


def _build_class(node: ast.ClassDef) -> ClassInfo:
    methods = [
        _build_function(child)
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    return ClassInfo(
        name=node.name,
        bases=[_name_of(b) for b in node.bases],
        docstring=ast.get_docstring(node),
        methods=methods,
        decorators=[_name_of(d) for d in node.decorator_list],
        lineno=node.lineno,
    )


def _collect_imports(tree: ast.Module) -> list[ImportInfo]:
    imports: list[ImportInfo] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportInfo(module=alias.name, names=[], level=0, is_from=False))
        elif isinstance(node, ast.ImportFrom):
            imports.append(
                ImportInfo(
                    module=node.module or "",
                    names=[a.name for a in node.names],
                    level=node.level or 0,
                    is_from=True,
                )
            )
    return imports


def module_name_for(path: Path, root: Path) -> str:
    """Compute a dotted module name for a file relative to the crawl root."""
    rel = path.relative_to(root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][: -len(".py")]
    return ".".join(parts)


def parse_file(path: Path, root: Path) -> ModuleInfo | None:
    """Parse a single .py file into a ModuleInfo. Returns None on syntax errors."""
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return None

    functions = [
        _build_function(node)
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    classes = [_build_class(node) for node in tree.body if isinstance(node, ast.ClassDef)]

    return ModuleInfo(
        path=path,
        rel_path=path.relative_to(root).as_posix(),
        module_name=module_name_for(path, root),
        docstring=ast.get_docstring(tree),
        imports=_collect_imports(tree),
        functions=functions,
        classes=classes,
    )


def iter_python_files(root: Path) -> list[Path]:
    """Recursively find every .py file under root, skipping junk directories."""
    found: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        found.append(path)
    return found


def parse_project(root: Path) -> list[ModuleInfo]:
    """Crawl a directory and parse every Python file into telemetry."""
    root = root.resolve()
    if root.is_file():
        info = parse_file(root, root.parent)
        return [info] if info else []
    modules = [parse_file(p, root) for p in iter_python_files(root)]
    return [m for m in modules if m is not None]
