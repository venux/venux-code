"""Title generation prompt.

Generates short, descriptive titles for chat sessions based on the
first user message or a summary of the conversation.
"""

from __future__ import annotations

from .base import PromptTemplate


TITLE_GENERATION_TEMPLATE = PromptTemplate(
    """\
Generate a short, descriptive title for a coding session based on the \
following message. The title should:

1. Be **concise** (3-8 words, max 60 characters)
2. **Describe the task**, not the conversation
3. Use **technical terms** when appropriate
4. **Not** include quotes, punctuation, or emojis
5. Be in the **same language** as the message

## Message

${message}

## Title""",
    name="title_generation",
)


TITLE_FROM_SUMMARY_TEMPLATE = PromptTemplate(
    """\
Generate a short, descriptive title for a coding session based on the \
following conversation summary. The title should:

1. Be **concise** (3-8 words, max 60 characters)
2. **Describe the main task** accomplished
3. Use **technical terms** when appropriate
4. **Not** include quotes, punctuation, or emojis

## Summary

${summary}

## Title""",
    name="title_from_summary",
)


def generate_title_prompt(message: str) -> str:
    """Render the title generation prompt from a user message.

    Parameters
    ----------
    message:
        The first user message in a session.

    Returns
    -------
    str
        The rendered prompt to send to the LLM.
    """
    # Truncate very long messages
    if len(message) > 2000:
        message = message[:2000] + "..."
    return TITLE_GENERATION_TEMPLATE.render(message=message)


def generate_title_from_summary_prompt(summary: str) -> str:
    """Render the title generation prompt from a conversation summary."""
    if len(summary) > 3000:
        summary = summary[:3000] + "..."
    return TITLE_FROM_SUMMARY_TEMPLATE.render(summary=summary)
