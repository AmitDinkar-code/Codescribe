"""Tests for Phase 1 — AST extraction."""

from __future__ import annotations

import textwrap
from pathlib import Path

from codescribe.parser import parse_file, parse_project


def _write(tmp_path: Path, name: str, src: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(src), encoding="utf-8")
    return p


def test_extracts_functions_classes_imports(tmp_path: Path) -> None:
    src = '''
        """Module docstring."""
        import os
        from typing import List

        def greet(name: str, loud: bool = False) -> str:
            """Say hello."""
            return os.linesep.join([name])

        class Greeter:
            """A greeter."""
            def hello(self, who: str) -> str:
                return greet(who)
    '''
    path = _write(tmp_path, "mod.py", src)
    info = parse_file(path, tmp_path)

    assert info is not None
    assert info.docstring == "Module docstring."
    assert info.module_name == "mod"

    # imports
    modules = {imp.module for imp in info.imports}
    assert "os" in modules
    assert "typing" in modules

    # functions
    fn = {f.name: f for f in info.functions}["greet"]
    assert fn.returns == "str"
    assert fn.args == ["name: str", "loud: bool = False"]
    assert fn.docstring == "Say hello."
    assert "os.linesep.join" in fn.calls

    # classes
    cls = info.classes[0]
    assert cls.name == "Greeter"
    assert cls.docstring == "A greeter."
    assert cls.methods[0].name == "hello"
    assert "greet" in cls.methods[0].calls


def test_signature_rendering(tmp_path: Path) -> None:
    src = "async def f(a, *args, b=1, **kw) -> None: ...\n"
    info = parse_file(_write(tmp_path, "s.py", src), tmp_path)
    assert info is not None
    sig = info.functions[0].signature
    assert sig.startswith("async def f(")
    assert "*args" in sig and "**kw" in sig and "-> None" in sig


def test_syntax_error_returns_none(tmp_path: Path) -> None:
    info = parse_file(_write(tmp_path, "bad.py", "def ( oops\n"), tmp_path)
    assert info is None


def test_parse_project_skips_pycache(tmp_path: Path) -> None:
    _write(tmp_path, "good.py", "x = 1\n")
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "junk.py").write_text("y = 2\n", encoding="utf-8")
    modules = parse_project(tmp_path)
    names = {m.module_name for m in modules}
    assert "good" in names
    assert not any("junk" in n for n in names)
