"""Venux Code CLI — Typer-based command-line interface.

Usage:
    venux-code                     Launch interactive TUI chat
    venux-code chat -q "prompt"    Single query (non-interactive)
    venux-code config              Show current configuration
    venux-code sessions list       List saved sessions
    venux-code doctor              Run health checks
    venux-code --version           Print version
"""

from __future__ import annotations

import asyncio
import sys
from typing import Optional

import typer

try:
    from venux_code import __version__
except (ImportError, AttributeError):
    __version__ = "0.1.0"

app = typer.Typer(
    name="venux-code",
    help="Venux Code — AI-powered coding assistant",
    no_args_is_help=False,
    add_completion=False,
)

sessions_app = typer.Typer(help="Manage chat sessions.")
app.add_typer(sessions_app, name="sessions")


# ---------------------------------------------------------------------------
# Default behaviour: no args → launch TUI
# ---------------------------------------------------------------------------

def _launch_tui() -> None:
    """Import and run the Textual TUI."""
    from venux_code.cli.app import bootstrap_and_run_tui

    asyncio.run(bootstrap_and_run_tui())


# ---------------------------------------------------------------------------
# chat — single query mode
# ---------------------------------------------------------------------------

@app.command()
def chat(
    query: str = typer.Option(..., "-q", "--query", help="Single prompt to send."),
    model: Optional[str] = typer.Option(None, "-m", "--model", help="Model override."),
    session_id: Optional[str] = typer.Option(None, "-s", "--session", help="Session ID to continue."),
    max_tokens: Optional[int] = typer.Option(None, "--max-tokens", help="Max response tokens."),
    no_stream: bool = typer.Option(False, "--no-stream", help="Disable streaming."),
) -> None:
    """Send a single query and print the response (non-interactive)."""
    asyncio.run(_chat(query=query, model=model, session_id=session_id, max_tokens=max_tokens, stream=not no_stream))


async def _chat(
    query: str,
    model: str | None,
    session_id: str | None,
    max_tokens: int | None,
    stream: bool,
) -> None:
    from venux_code.cli.app import bootstrap_agent

    agent, session = await bootstrap_agent(model=model, session_id=session_id)

    from rich.console import Console
    from rich.live import Live
    from rich.markdown import Markdown

    console = Console()

    if stream:
        full_text = ""
        with Live(console=console, refresh_per_second=12) as live:
            async for chunk in agent.stream(query, max_tokens=max_tokens):
                full_text += chunk
                live.update(Markdown(full_text))
    else:
        with console.status("[bold green]Thinking…"):
            response = await agent.run(query, max_tokens=max_tokens)
        console.print(Markdown(response))

    await session.close()


# ---------------------------------------------------------------------------
# config — show current configuration
# ---------------------------------------------------------------------------

@app.command(name="config")
def show_config() -> None:
    """Display the current Venux Code configuration."""
    from rich.console import Console
    from rich.table import Table

    # Show the lightweight VenuxConfig
    from venux_code.cli.app import load_config
    cfg = load_config()

    # Also try to show Settings-based config
    try:
        from venux_code.config.settings import get_settings
        settings = get_settings()
        cfg["llm_provider"] = settings.llm.provider
        cfg["llm_model"] = settings.llm.model
        cfg["db_url"] = settings.db_url
        cfg["data_dir"] = str(settings.data_dir)
        cfg["debug"] = settings.debug
    except Exception:
        pass

    console = Console()
    table = Table(title="Venux Code Configuration", show_lines=True)
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")

    for key, value in cfg.items():
        table.add_row(str(key), str(value))

    console.print(table)


# ---------------------------------------------------------------------------
# sessions list
# ---------------------------------------------------------------------------

@sessions_app.command("list")
def sessions_list(
    limit: int = typer.Option(20, "-n", "--limit", help="Max sessions to show."),
) -> None:
    """List saved chat sessions."""
    asyncio.run(_sessions_list(limit=limit))


async def _sessions_list(limit: int) -> None:
    from venux_code.cli.app import load_sessions
    from rich.console import Console
    from rich.table import Table

    sessions = await load_sessions(limit=limit)
    console = Console()

    if not sessions:
        console.print("[yellow]No sessions found.[/yellow]")
        return

    table = Table(title="Chat Sessions", show_lines=True)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Title", style="white")
    table.add_column("Created", style="dim")
    table.add_column("Messages", justify="right", style="green")

    for s in sessions:
        table.add_row(s["id"], s.get("title", "—"), s.get("created_at", "—"), str(s.get("message_count", 0)))

    console.print(table)


# ---------------------------------------------------------------------------
# doctor — health check
# ---------------------------------------------------------------------------

@app.command()
def doctor() -> None:
    """Run health checks on configuration, database, and LLM connectivity."""
    asyncio.run(_doctor())


async def _doctor() -> None:
    from rich.console import Console

    console = Console()
    console.print("[bold]Venux Code Doctor[/bold]\n")
    checks: list[tuple[str, bool, str]] = []

    # 1. Config
    try:
        from venux_code.cli.app import load_config
        cfg = load_config()
        checks.append(("Configuration", True, "Loaded successfully"))
    except Exception as exc:
        checks.append(("Configuration", False, str(exc)))

    # 2. Settings (pydantic-based)
    try:
        from venux_code.config.settings import get_settings
        settings = get_settings()
        checks.append(("Settings", True, f"provider={settings.llm.provider} model={settings.llm.model}"))
    except Exception as exc:
        checks.append(("Settings", False, str(exc)))

    # 3. Database
    try:
        from venux_code.cli.app import check_database
        await check_database()
        checks.append(("Database", True, "Connected"))
    except Exception as exc:
        checks.append(("Database", False, str(exc)))

    # 4. DB init (create tables)
    try:
        from venux_code.db.engine import init_db
        await init_db()
        checks.append(("DB Tables", True, "Created/verified"))
    except Exception as exc:
        checks.append(("DB Tables", False, str(exc)))

    # 5. Tools
    try:
        from venux_code.llm.tools.registry import ToolRegistry
        registry = ToolRegistry()
        tool_names = registry.list_names()
        checks.append(("Tools", True, f"{len(tool_names)} registered: {', '.join(tool_names[:5])}{'…' if len(tool_names) > 5 else ''}"))
    except Exception as exc:
        checks.append(("Tools", False, str(exc)))

    # 6. LLM provider
    try:
        from venux_code.llm.providers.registry import create_provider
        provider = create_provider()
        info = provider.model_info()
        checks.append(("LLM Provider", True, f"{info.provider}/{info.name}"))
    except Exception as exc:
        checks.append(("LLM Provider", False, str(exc)))

    # 7. LLM connectivity (only if key is available)
    try:
        from venux_code.cli.app import check_llm
        await check_llm()
        checks.append(("LLM connectivity", True, "Reachable"))
    except Exception as exc:
        checks.append(("LLM connectivity", False, str(exc)))

    # 8. Dependencies
    try:
        import textual  # noqa: F401
        import rich  # noqa: F401
        import langchain_core  # noqa: F401
        import langgraph  # noqa: F401
        checks.append(("Dependencies", True, "textual, rich, langchain, langgraph installed"))
    except ImportError as exc:
        checks.append(("Dependencies", False, f"Missing: {exc}"))

    # Render
    all_ok = True
    for name, ok, detail in checks:
        icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
        console.print(f"  {icon} {name}: {detail}")
        if not ok:
            all_ok = False

    if all_ok:
        console.print("\n[bold green]All checks passed.[/bold green]")
    else:
        console.print("\n[bold yellow]Some checks failed (this is OK if no API key is set).[/bold yellow]")


# ---------------------------------------------------------------------------
# --version
# ---------------------------------------------------------------------------

def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"venux-code {__version__}")
        raise typer.Exit()


@app.command(hidden=True)
def version() -> None:
    """Show version."""
    typer.echo(f"venux-code {__version__}")


# Single unified callback
@app.callback(invoke_without_command=True)
def _main(
    ctx: typer.Context,
    version_flag: Optional[bool] = typer.Option(None, "--version", "-V", is_eager=True, callback=_version_callback, help="Show version and exit."),
) -> None:
    """Venux Code — AI coding assistant.  Run without arguments for TUI."""
    if ctx.invoked_subcommand is None:
        _launch_tui()
