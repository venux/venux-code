"""HTTP fetch tool – retrieves content from a URL.

Uses ``httpx`` for async HTTP requests.  Returns text or JSON content.
Supports GET/POST, custom headers, and configurable timeouts.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field

from .base import BaseTool, ToolResponse


class FetchParams(BaseModel):
    """Parameters for the fetch tool."""

    url: str = Field(description="The URL to fetch.")
    method: str = Field(
        default="GET",
        description="HTTP method: GET or POST.",
    )
    headers: Optional[dict[str, str]] = Field(
        default=None,
        description="Optional HTTP headers.",
    )
    body: Optional[str] = Field(
        default=None,
        description="Request body (for POST). Sent as raw text.",
    )
    timeout: int = Field(
        default=30,
        ge=1,
        le=120,
        description="Request timeout in seconds.",
    )
    max_chars: int = Field(
        default=50_000,
        description="Maximum characters to return. Longer responses are truncated.",
    )
    follow_redirects: bool = Field(
        default=True,
        description="Whether to follow HTTP redirects.",
    )


class FetchTool(BaseTool):
    """Fetch a URL and return its content as text or JSON."""

    name = "fetch"
    description = (
        "Fetch content from a URL using HTTP GET or POST. "
        "Returns the response body as text. Use this to read web pages, "
        "API endpoints, or download files."
    )
    parameters_schema = FetchParams
    requires_permission = False

    async def execute(self, params: dict[str, Any]) -> ToolResponse:
        validated = FetchParams(**params)

        try:
            async with httpx.AsyncClient(
                timeout=validated.timeout,
                follow_redirects=validated.follow_redirects,
            ) as client:
                method = validated.method.upper()
                kwargs: dict[str, Any] = {
                    "url": validated.url,
                    "headers": validated.headers or {},
                }
                if method == "POST" and validated.body is not None:
                    kwargs["content"] = validated.body

                response = await client.request(method, **kwargs)

            content_type = response.headers.get("content-type", "")
            is_json = "json" in content_type

            if is_json:
                try:
                    data = response.json()
                    text = str(data)
                except Exception:
                    text = response.text
            else:
                text = response.text

            # Truncate
            if len(text) > validated.max_chars:
                text = text[: validated.max_chars] + "\n... (truncated)"

            return ToolResponse(
                success=True,
                output=text,
                metadata={
                    "status_code": response.status_code,
                    "content_type": content_type,
                    "url": str(response.url),
                    "length": len(text),
                },
                display_type="code" if is_json else "text",
            )

        except httpx.TimeoutException:
            return ToolResponse(
                success=False,
                error=f"Request timed out after {validated.timeout}s: {validated.url}",
            )
        except httpx.RequestError as exc:
            return ToolResponse(
                success=False,
                error=f"Request failed: {exc}",
            )
        except Exception as exc:
            return ToolResponse(
                success=False,
                error=f"Fetch error: {exc}",
            )
