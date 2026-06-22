"""Sub-agent delegation tool.

Spawns an isolated agent session to handle a sub-task, then returns the
result to the parent agent.  Useful for breaking complex problems into
independent pieces that can be solved in parallel.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field

from .base import BaseTool, ToolResponse

logger = logging.getLogger(__name__)


class DelegateParams(BaseModel):
    """Parameters for the delegate tool."""

    task: str = Field(
        description="The task description to delegate to the sub-agent.",
    )
    skills: list[str] = Field(
        default_factory=list,
        description="Skill names to load for the sub-agent session.",
    )
    max_iterations: int = Field(
        default=20,
        ge=1,
        le=50,
        description="Maximum agent loop iterations for the sub-agent.",
    )
    timeout: int = Field(
        default=120,
        ge=10,
        le=600,
        description="Maximum seconds to wait for the sub-agent to complete.",
    )
    context: Optional[str] = Field(
        default=None,
        description="Additional context to include in the sub-agent's system prompt.",
    )


class DelegateTool(BaseTool):
    """Delegate a task to an isolated sub-agent."""

    name = "delegate"
    description = (
        "Delegate a sub-task to an isolated agent. The sub-agent runs "
        "independently with its own context and tools. Use this to break "
        "complex problems into smaller pieces, run parallel investigations, "
        "or isolate potentially risky operations. Returns the sub-agent's "
        "final output."
    )
    parameters_schema = DelegateParams
    requires_permission = False

    def __init__(
        self,
        *,
        agent_factory: Any | None = None,
        default_tools: list[Any] | None = None,
        default_system_prompt: str | None = None,
    ) -> None:
        """Create the delegate tool.

        Parameters
        ----------
        agent_factory:
            Async callable ``(prompt, skills, session_id, ...) -> str``
            that creates and runs an agent session.
        default_tools:
            Tools available to sub-agents (LangChain tool objects).
        default_system_prompt:
            Base system prompt for sub-agents.
        """
        self._agent_factory = agent_factory
        self._default_tools = default_tools or []
        self._default_system_prompt = default_system_prompt

    async def execute(self, params: dict[str, Any]) -> ToolResponse:
        validated = DelegateParams(**params)
        session_id = f"delegate-{uuid.uuid4().hex[:12]}"

        logger.info(
            "Delegating task to sub-agent (session=%s, skills=%s)",
            session_id,
            validated.skills,
        )

        # Build the delegation prompt
        parts: list[str] = []
        if validated.context:
            parts.append(f"## Additional Context\n{validated.context}\n")
        parts.append(f"## Task\n{validated.task}")

        full_prompt = "\n".join(parts)

        try:
            if self._agent_factory is not None:
                # Use the provided factory
                result = await asyncio.wait_for(
                    self._agent_factory(
                        prompt=full_prompt,
                        skills=validated.skills,
                        session_id=session_id,
                    ),
                    timeout=validated.timeout,
                )
            else:
                # Fallback: create a minimal agent inline
                result = await asyncio.wait_for(
                    self._run_fallback_agent(
                        full_prompt,
                        session_id,
                        validated.skills,
                        validated.max_iterations,
                    ),
                    timeout=validated.timeout,
                )

            logger.info(
                "Sub-agent %s completed (%d chars output)",
                session_id,
                len(result),
            )

            return ToolResponse(
                success=True,
                output=result,
                metadata={
                    "session_id": session_id,
                    "skills": validated.skills,
                    "output_length": len(result),
                },
                display_type="text",
            )

        except asyncio.TimeoutError:
            return ToolResponse(
                success=False,
                error=f"Sub-agent timed out after {validated.timeout}s",
                metadata={"session_id": session_id},
            )
        except Exception as exc:
            logger.exception("Sub-agent %s failed", session_id)
            return ToolResponse(
                success=False,
                error=f"Sub-agent failed: {exc}",
                metadata={"session_id": session_id},
            )

    async def _run_fallback_agent(
        self,
        prompt: str,
        session_id: str,
        skills: list[str],
        max_iterations: int,
    ) -> str:
        """Fallback: use the VenuxAgent directly if no factory is provided."""
        from langchain_core.messages import HumanMessage, SystemMessage

        from venux_code.llm.agent.agent import VenuxAgent
        from venux_code.llm.providers.registry import create_provider
        from venux_code.config.settings import get_settings

        settings = get_settings()
        provider = create_provider(settings=settings)
        model = provider._build_model()

        system_parts: list[str] = []
        if self._default_system_prompt:
            system_parts.append(self._default_system_prompt)
        if skills:
            system_parts.append(f"Active skills: {', '.join(skills)}")
        system_parts.append(
            "You are a sub-agent. Complete the assigned task and return "
            "your findings. Be concise and thorough."
        )

        system_prompt = "\n\n".join(system_parts)

        agent = VenuxAgent(
            model=model,
            tools=self._default_tools or [],
            system_prompt=system_prompt,
            max_iterations=max_iterations,
        )

        # Collect all output tokens
        output_parts: list[str] = []
        async for event in agent.run(prompt, session_id=session_id):
            from venux_code.llm.agent.agent import AgentEventType

            if event.type == AgentEventType.LLM_TOKEN:
                output_parts.append(event.data.get("token", ""))
            elif event.type == AgentEventType.AGENT_DONE:
                break
            elif event.type == AgentEventType.ERROR:
                raise RuntimeError(event.data.get("error", "Unknown error"))

        return "".join(output_parts)
