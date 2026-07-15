"""Pydantic output schemas for the documentation pipeline.

These models are the strict contract the LLM must satisfy (Phase 3). They are
deliberately kept flat and free of numeric/length constraints, which the
structured-outputs JSON schema does not support — the Anthropic SDK strips
unsupported constraints and validates them client-side, but keeping the schema
clean avoids surprises.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FunctionDoc(BaseModel):
    """Documentation for a single function."""

    name: str = Field(description="The function name as it appears in source.")
    signature: str = Field(description="Rendered signature, e.g. 'def f(a: int) -> str'.")
    summary: str = Field(description="One-sentence description of what the function does.")
    parameters: list[str] = Field(
        default_factory=list,
        description="Human-readable description of each parameter, one entry per parameter.",
    )
    returns: str = Field(default="", description="What the function returns, if anything.")


class ClassDoc(BaseModel):
    """Documentation for a single class."""

    name: str = Field(description="The class name.")
    summary: str = Field(description="One-sentence description of the class's purpose.")
    key_methods: list[str] = Field(
        default_factory=list,
        description="Names (or 'name — purpose') of the most important methods.",
    )


class ModuleDoc(BaseModel):
    """Documentation for a single module (file)."""

    path: str = Field(description="Module path relative to the project root, e.g. 'pkg/mod.py'.")
    summary: str = Field(description="One-paragraph summary of the module's responsibility.")
    responsibilities: list[str] = Field(
        default_factory=list,
        description="Bullet list of the module's main responsibilities.",
    )
    functions: list[FunctionDoc] = Field(default_factory=list)
    classes: list[ClassDoc] = Field(default_factory=list)


class DependencyCycleWarning(BaseModel):
    """A detected cyclic import dependency and how to resolve it."""

    cycle: list[str] = Field(
        description="Ordered module chain forming the cycle, e.g. ['a', 'b', 'a']."
    )
    severity: str = Field(description="One of: low, medium, high.")
    explanation: str = Field(description="Why this cycle is a problem.")
    suggested_fix: str = Field(description="A concrete way to break the cycle.")


class ProjectDoc(BaseModel):
    """Top-level documentation artifact rendered into the README."""

    project_name: str = Field(description="A concise, human-friendly project name.")
    overview: str = Field(description="A few sentences describing what the project does.")
    architecture: str = Field(
        description="A paragraph describing how the modules fit together."
    )
    installation: str = Field(description="Markdown installation instructions.")
    usage: str = Field(description="Markdown usage instructions / examples.")
    modules: list[ModuleDoc] = Field(default_factory=list)
    dependency_cycles: list[DependencyCycleWarning] = Field(default_factory=list)
