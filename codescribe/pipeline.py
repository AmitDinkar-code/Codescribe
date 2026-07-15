"""Phase 3 — AI pipeline & Pydantic validation.

Feeds the Phase-1 telemetry and Phase-2 graph paths into Claude and forces the
response to satisfy the Pydantic schema in `models.py` using the Anthropic SDK's
structured-output support (`client.messages.parse(..., output_format=...)`).

A deterministic, no-LLM fallback is also provided so the full pipeline can be
exercised (and tested) without an API key.
"""

from __future__ import annotations

import json

from .graph import DependencyGraph, find_cycles
from .models import (
    ClassDoc,
    DependencyCycleWarning,
    FunctionDoc,
    ModuleDoc,
    ProjectDoc,
)
from .parser import ModuleInfo

DEFAULT_MODEL = "claude-opus-4-8"
MAX_TOKENS = 16000

SYSTEM_PROMPT = (
    "You are a senior software engineer writing precise, accurate developer "
    "documentation. You are given deterministic telemetry extracted from a "
    "Python codebase via static analysis (AST), plus a list of cyclic import "
    "dependencies found by graph traversal. Document ONLY what the telemetry "
    "supports — never invent functions, classes, parameters, or behavior that "
    "is not present. Prefer the code's own docstrings where available. Keep "
    "summaries concise and technical."
)


def build_payload(
    modules: list[ModuleInfo],
    cycles: list[list[str]],
    name_hint: str | None = None,
) -> dict:
    """Assemble the deterministic telemetry payload handed to the model."""
    return {
        "project_name_hint": name_hint,
        "modules": [m.to_telemetry() for m in modules],
        "dependency_cycles": cycles,
    }


def _user_prompt(payload: dict) -> str:
    return (
        "Here is the extracted telemetry for a Python project as JSON.\n\n"
        "```json\n"
        f"{json.dumps(payload, indent=2)}\n"
        "```\n\n"
        "Produce structured documentation for the whole project. For every "
        "module include its functions and classes. For each detected dependency "
        "cycle, assign a severity, explain why it is problematic, and suggest a "
        "concrete fix. Write installation and usage sections appropriate for a "
        "Python project of this shape."
    )


def generate_with_llm(
    payload: dict,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
) -> ProjectDoc:
    """Call Claude and return a schema-validated ProjectDoc.

    Requires the `anthropic` package and credentials (ANTHROPIC_API_KEY or an
    `ant auth login` profile). Raises on import/credential/validation failure so
    the caller can decide whether to fall back.
    """
    import anthropic  # imported lazily so --no-llm works without the package

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    response = client.messages.parse(
        model=model,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _user_prompt(payload)}],
        output_format=ProjectDoc,
    )

    if response.parsed_output is None:
        raise RuntimeError(
            f"Model did not return schema-valid output (stop_reason={response.stop_reason})."
        )
    return response.parsed_output


def _severity_for(cycle: list[str]) -> str:
    # A tight 2-module cycle is the most pernicious; longer chains are looser.
    distinct = len(set(cycle))
    if distinct <= 2:
        return "high"
    if distinct <= 4:
        return "medium"
    return "low"


def generate_offline(payload: dict) -> ProjectDoc:
    """Deterministically build a ProjectDoc from telemetry, with no LLM.

    Useful for tests, CI, and running without credentials. It leans on the
    code's own docstrings rather than synthesising prose.
    """
    modules_doc: list[ModuleDoc] = []
    for m in payload["modules"]:
        functions = [
            FunctionDoc(
                name=fn["name"],
                signature=fn["signature"],
                summary=_first_sentence(fn.get("docstring")) or f"Function `{fn['name']}`.",
                parameters=[],
                returns="",
            )
            for fn in m.get("functions", [])
        ]
        classes = [
            ClassDoc(
                name=cls["name"],
                summary=_first_sentence(cls.get("docstring")) or f"Class `{cls['name']}`.",
                key_methods=[meth["name"] for meth in cls.get("methods", []) if meth["name"] != "__init__"],
            )
            for cls in m.get("classes", [])
        ]
        modules_doc.append(
            ModuleDoc(
                path=m["path"],
                summary=_first_paragraph(m.get("docstring")) or f"Module `{m['module']}`.",
                responsibilities=_responsibilities(m),
                functions=functions,
                classes=classes,
            )
        )

    cycles_doc = [
        DependencyCycleWarning(
            cycle=cycle,
            severity=_severity_for(cycle),
            explanation=(
                "These modules import each other, forming a cycle. Cyclic imports "
                "make initialization order fragile, can cause ImportError at "
                "runtime, and couple the modules so they cannot be understood or "
                "tested in isolation."
            ),
            suggested_fix=(
                "Extract the shared types/functions into a third module that both "
                "depend on, defer one import to inside the function that needs it, "
                "or merge the modules if the split is artificial."
            ),
        )
        for cycle in payload.get("dependency_cycles", [])
    ]

    name = _infer_name(payload)
    return ProjectDoc(
        project_name=name,
        overview=(
            f"`{name}` is a Python project containing "
            f"{len(modules_doc)} module(s). This documentation was generated by "
            "static analysis of the source (no code was executed)."
        ),
        architecture=_architecture_text(payload),
        installation=(
            "```bash\n"
            "git clone <repo-url>\n"
            f"cd {name}\n"
            "pip install -e .\n"
            "```"
        ),
        usage=(
            "Import the modules you need and call their functions/classes "
            "directly. See the per-module reference below."
        ),
        modules=modules_doc,
        dependency_cycles=cycles_doc,
    )


def generate(
    payload: dict,
    *,
    use_llm: bool = True,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
) -> tuple[ProjectDoc, str]:
    """Generate a ProjectDoc, returning it alongside the mode actually used.

    Falls back to the offline generator if the LLM path is unavailable.
    """
    if not use_llm:
        return generate_offline(payload), "offline"
    try:
        return generate_with_llm(payload, model=model, api_key=api_key), "llm"
    except Exception as exc:  # noqa: BLE001 — surface the reason, then fall back
        print(f"[codescribe] LLM generation unavailable ({exc}); using offline fallback.")
        return generate_offline(payload), "offline"


# --- small text helpers for the offline generator ---------------------------


def _first_sentence(text: str | None) -> str:
    if not text:
        return ""
    first = text.strip().split("\n", 1)[0].strip()
    for sep in (". ", ".\n"):
        if sep in first:
            return first.split(sep, 1)[0].strip() + "."
    return first


def _first_paragraph(text: str | None) -> str:
    if not text:
        return ""
    return text.strip().split("\n\n", 1)[0].replace("\n", " ").strip()


def _responsibilities(module: dict) -> list[str]:
    out: list[str] = []
    for cls in module.get("classes", []):
        out.append(f"Defines class `{cls['name']}`")
    fns = [fn["name"] for fn in module.get("functions", [])]
    if fns:
        preview = ", ".join(f"`{n}`" for n in fns[:5])
        out.append(f"Provides function(s): {preview}")
    return out


def _architecture_text(payload: dict) -> str:
    n = len(payload["modules"])
    cyc = len(payload.get("dependency_cycles", []))
    base = (
        f"The project is organised into {n} module(s) connected through their "
        "import relationships."
    )
    if cyc:
        base += (
            f" Static analysis found {cyc} cyclic import dependency(ies), flagged "
            "below — these are the highest-risk coupling points in the codebase."
        )
    else:
        base += " No cyclic import dependencies were detected."
    return base


def _infer_name(payload: dict) -> str:
    hint = payload.get("project_name_hint")
    if hint:
        return hint
    for m in payload["modules"]:
        top = m["module"].split(".")[0]
        if top and not (top.startswith("__") and top.endswith("__")):
            return top
    return "project"


def graph_cycles(graph: DependencyGraph) -> list[list[str]]:
    """Convenience wrapper so callers don't import find_cycles separately."""
    return find_cycles(graph)
