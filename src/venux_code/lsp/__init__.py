"""LSP integration for Venux Code.

Provides an async LSP client, Pydantic models, configuration loading,
and an LLM tool for retrieving diagnostics.
"""

from .client import LSPClient, LSPClientError
from .config import LSPConfig, LSPServerConfig
from .models import Diagnostic, DiagnosticSeverity, Position, Range

__all__ = [
    "Diagnostic",
    "DiagnosticSeverity",
    "LSPClient",
    "LSPClientError",
    "LSPConfig",
    "LSPServerConfig",
    "Position",
    "Range",
]
