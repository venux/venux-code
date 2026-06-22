"""Web search tool – DuckDuckGo / SearXNG integration.

Provides web search capability for the agent.  Supports two backends:
  - **DuckDuckGo** (default, no API key required)
  - **SearXNG** (self-hosted, configurable instance URL)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field

from .base import BaseTool, ToolResponse

logger = logging.getLogger(__name__)


class WebSearchParams(BaseModel):
    """Parameters for the web search tool."""

    query: str = Field(description="The search query string.")
    max_results: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of results to return.",
    )
    backend: str = Field(
        default="duckduckgo",
        description="Search backend: 'duckduckgo' or 'searxng'.",
    )
    searxng_url: Optional[str] = Field(
        default=None,
        description="SearXNG instance URL (required if backend='searxng').",
    )


class WebSearchTool(BaseTool):
    """Search the web using DuckDuckGo or SearXNG."""

    name = "web_search"
    description = (
        "Search the web for information. Returns a list of results with "
        "titles, URLs, and snippets. Use this to find documentation, "
        "answer questions, or research topics."
    )
    parameters_schema = WebSearchParams
    requires_permission = False

    async def execute(self, params: dict[str, Any]) -> ToolResponse:
        validated = WebSearchParams(**params)

        try:
            if validated.backend == "searxng":
                results = await self._search_searxng(
                    validated.query,
                    validated.max_results,
                    validated.searxng_url,
                )
            else:
                results = await self._search_ddg(
                    validated.query,
                    validated.max_results,
                )

            if not results:
                return ToolResponse(
                    success=True,
                    output="No results found.",
                    metadata={"query": validated.query, "count": 0},
                )

            # Format results
            lines: list[str] = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "Untitled")
                url = r.get("url", "")
                snippet = r.get("snippet", "")
                lines.append(f"{i}. **{title}**")
                lines.append(f"   URL: {url}")
                if snippet:
                    lines.append(f"   {snippet}")
                lines.append("")

            return ToolResponse(
                success=True,
                output="\n".join(lines),
                metadata={
                    "query": validated.query,
                    "count": len(results),
                    "backend": validated.backend,
                },
                display_type="markdown",
            )

        except Exception as exc:
            return ToolResponse(
                success=False,
                error=f"Search failed: {exc}",
                metadata={"query": validated.query},
            )

    # ── DuckDuckGo ──────────────────────────────────────────────────────────

    @staticmethod
    async def _search_ddg(query: str, max_results: int) -> list[dict[str, str]]:
        """Search via DuckDuckGo Instant Answer API + HTML fallback."""
        results: list[dict[str, str]] = []

        # Try the HTML lite version first
        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; VenuxCode/1.0; "
                "+https://github.com/nousresearch/venux-code)"
            )
        }

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.post(url, data={"q": query}, headers=headers)
            resp.raise_for_status()
            html = resp.text

        # Simple HTML parsing without BeautifulSoup
        import re

        # Find result links and snippets
        # Pattern: <a rel="nofollow" class="result__a" href="URL">TITLE</a>
        # followed by <a class="result__snippet" ...>SNIPPET</a>
        link_pattern = re.compile(
            r'class="result__a"\s+href="([^"]+)"[^>]*>(.*?)</a>',
            re.DOTALL,
        )
        snippet_pattern = re.compile(
            r'class="result__snippet"[^>]*>(.*?)</a>',
            re.DOTALL,
        )

        links = link_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i, (href, title) in enumerate(links[:max_results]):
            # Clean HTML tags from title
            clean_title = re.sub(r"<[^>]+>", "", title).strip()
            snippet = ""
            if i < len(snippets):
                snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()

            # DuckDuckGo redirects through their own URL
            if "uddg=" in href:
                import urllib.parse
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                href = parsed.get("uddg", [href])[0]

            results.append({
                "title": clean_title,
                "url": href,
                "snippet": snippet,
            })

        return results

    # ── SearXNG ─────────────────────────────────────────────────────────────

    @staticmethod
    async def _search_searxng(
        query: str,
        max_results: int,
        instance_url: str | None,
    ) -> list[dict[str, str]]:
        """Search via a SearXNG instance JSON API."""
        if not instance_url:
            raise ValueError("searxng_url is required for SearXNG backend")

        # Ensure trailing slash
        base = instance_url.rstrip("/")
        url = f"{base}/search"
        params = {
            "q": query,
            "format": "json",
            "pageno": 1,
        }

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        results: list[dict[str, str]] = []
        for item in data.get("results", [])[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
            })

        return results
