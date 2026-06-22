"""Pydantic models for the Language Server Protocol (LSP) subset used by Venux Code."""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


class DiagnosticSeverity(IntEnum):
    """LSP diagnostic severity levels."""

    ERROR = 1
    WARNING = 2
    INFORMATION = 3
    HINT = 4


class Position(BaseModel):
    """Zero-based position in a text document."""

    line: int = Field(ge=0, description="Zero-based line number.")
    character: int = Field(ge=0, description="Zero-based character offset.")


class Range(BaseModel):
    """A range in a text document expressed as start/end positions."""

    start: Position
    end: Position


class Diagnostic(BaseModel):
    """A single diagnostic reported by an LSP server."""

    range: Range
    severity: Optional[DiagnosticSeverity] = None
    code: Optional[int | str] = None
    source: Optional[str] = None
    message: str
    tags: list[int] = Field(default_factory=list)
    related_information: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def severity_label(self) -> str:
        """Human-readable severity label."""
        if self.severity is None:
            return "unknown"
        return {
            DiagnosticSeverity.ERROR: "error",
            DiagnosticSeverity.WARNING: "warning",
            DiagnosticSeverity.INFORMATION: "info",
            DiagnosticSeverity.HINT: "hint",
        }.get(self.severity, "unknown")

    def format_for_display(self, file_uri: str = "") -> str:
        """Return a human-readable one-line summary."""
        loc = f"{self.range.start.line + 1}:{self.range.start.character + 1}"
        src = f" [{self.source}]" if self.source else ""
        code = f" ({self.code})" if self.code is not None else ""
        prefix = file_uri.split("/")[-1] if file_uri else ""
        file_part = f"{prefix}:" if prefix else ""
        return f"{file_part}{loc} {self.severity_label}{src}{code}: {self.message}"
