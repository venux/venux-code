"""Context summarization / compression prompt.

Used to compress long conversation histories or file contents into a
concise summary that preserves the most important information.
"""

from __future__ import annotations

from .base import PromptTemplate


# ── Conversation summarization ──────────────────────────────────────────────

CONVERSATION_SUMMARIZE_TEMPLATE = PromptTemplate(
    """\
You are a context compression assistant. Your job is to summarize a \
conversation history into a concise, information-dense summary that \
preserves all important context for continuing the conversation.

## Guidelines

1. **Preserve key decisions** and their rationale.
2. **Keep file paths**, function names, and code references.
3. **Retain error messages** and their resolutions.
4. **Include pending tasks** or unfinished work.
5. **Remove redundant** explanations and pleasantries.
6. **Use bullet points** for clarity.
7. **Target length**: ~${target_ratio}% of original.

## Conversation to Summarize

${conversation}

## Summary

Provide a structured summary with these sections:
- **Work Completed**: What was done
- **Key Decisions**: Important choices made
- **Files Modified**: List of files changed
- **Current State**: Where things stand now
- **Pending Work**: What still needs to be done
- **Important Context**: Anything needed to continue""",
    name="conversation_summarize",
)


# ── File content summarization ──────────────────────────────────────────────

FILE_SUMMARIZE_TEMPLATE = PromptTemplate(
    """\
Summarize the following file content. Focus on:
1. **Purpose**: What this file does
2. **Key exports**: Main classes, functions, constants
3. **Dependencies**: What it imports / relies on
4. **Structure**: How the code is organized
5. **Notable patterns**: Design patterns, conventions used

## File: ${file_path}

\`\`\`${language}
${content}
\`\`\`

## Summary""",
    name="file_summarize",
)


# ── Error summarization ────────────────────────────────────────────────────

ERROR_SUMMARIZE_TEMPLATE = PromptTemplate(
    """\
Analyze the following error and provide:
1. **Root cause**: What likely caused this error
2. **Fix**: How to resolve it
3. **Prevention**: How to avoid it in the future

## Error

\`\`\`
${error_output}
\`\`\`

## Related Code Context

${code_context}

## Analysis""",
    name="error_summarize",
)


# ── Helper functions ────────────────────────────────────────────────────────


def summarize_conversation(
    conversation: str,
    *,
    target_ratio: int = 30,
) -> str:
    """Render the conversation summarization prompt.

    Parameters
    ----------
    conversation:
        The conversation text to summarize.
    target_ratio:
        Target summary length as percentage of original.

    Returns
    -------
    str
        The rendered prompt to send to the LLM.
    """
    return CONVERSATION_SUMMARIZE_TEMPLATE.render(
        conversation=conversation,
        target_ratio=target_ratio,
    )


def summarize_file(file_path: str, content: str, language: str = "") -> str:
    """Render the file summarization prompt."""
    if not language:
        # Guess from extension
        ext = file_path.rsplit(".", 1)[-1] if "." in file_path else ""
        language = ext or "text"
    return FILE_SUMMARIZE_TEMPLATE.render(
        file_path=file_path,
        content=content,
        language=language,
    )


def summarize_error(error_output: str, code_context: str = "") -> str:
    """Render the error summarization prompt."""
    return ERROR_SUMMARIZE_TEMPLATE.render(
        error_output=error_output,
        code_context=code_context or "(no additional context)",
    )
