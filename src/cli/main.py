"""Infra-Aware RAG CLI - Query your Azure infrastructure.

This module provides a command-line interface for interacting with the
Infra-Aware RAG system, allowing users to:
- Chat with the infrastructure assistant
- Search across Azure resources, Terraform, and Git history
- Execute Azure Resource Graph queries directly
"""

import asyncio
import json
import os
import subprocess
import sys
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

app = typer.Typer(
    name="infra-rag",
    help="Infra-Aware RAG CLI - Query your Azure infrastructure",
    no_args_is_help=True,
)
console = Console()

# Default configuration - can be overridden by environment variables
DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1"


def get_api_base_url() -> str:
    """Get the API base URL from environment or default."""
    return os.getenv("INFRA_RAG_API_URL", DEFAULT_API_BASE_URL)


async def get_token() -> str:
    """Get authentication token using Azure CLI.

    Falls back to returning an empty string if Azure CLI is not available
    or not logged in, which allows local development without auth.

    Returns:
        Bearer token string, or empty string if not available
    """
    try:
        result = subprocess.run(
            [
                "az",
                "account",
                "get-access-token",
                "--resource",
                "https://management.azure.com/",
                "--query",
                "accessToken",
                "-o",
                "tsv",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            return result.stdout.strip()
        else:
            console.print(
                "[yellow]Warning: Could not get Azure CLI token. "
                "Running without authentication.[/yellow]"
            )
            return ""

    except FileNotFoundError:
        console.print(
            "[yellow]Warning: Azure CLI not found. "
            "Running without authentication.[/yellow]"
        )
        return ""
    except subprocess.TimeoutExpired:
        console.print(
            "[yellow]Warning: Azure CLI timed out. "
            "Running without authentication.[/yellow]"
        )
        return ""


def get_headers(token: str) -> dict[str, str]:
    """Get request headers including authorization if token is available."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


@app.command()
def chat(
    query: str = typer.Argument(
        None,
        help="Initial query (starts interactive mode if not provided)",
    ),
    subscription: str = typer.Option(
        None,
        "--subscription",
        "-s",
        help="Filter to specific Azure subscription ID",
    ),
    api_url: str = typer.Option(
        None,
        "--api-url",
        "-u",
        help="API base URL (overrides INFRA_RAG_API_URL env var)",
        envvar="INFRA_RAG_API_URL",
    ),
) -> None:
    """Start an interactive chat session or ask a single question.

    Examples:
        infra-rag chat                          # Interactive mode
        infra-rag chat "List all VMs"           # Single query
        infra-rag chat -s <sub-id> "List VMs"   # Filter by subscription
    """
    base_url = api_url or get_api_base_url()

    if query:
        # Single query mode
        asyncio.run(_single_query(query, subscription, base_url))
    else:
        # Interactive mode
        asyncio.run(_interactive_chat(subscription, base_url))


async def _single_query(
    query: str,
    subscription: str | None,
    base_url: str,
) -> None:
    """Execute a single query and display the result."""
    token = await get_token()
    headers = get_headers(token)

    async with httpx.AsyncClient(timeout=120.0) as client:
        # Create conversation
        try:
            metadata: dict[str, Any] = {}
            if subscription:
                metadata["subscription"] = subscription

            conv_resp = await client.post(
                f"{base_url}/conversations",
                headers=headers,
                json={"metadata": metadata} if metadata else None,
            )
            conv_resp.raise_for_status()
            conv_id = conv_resp.json()["id"]
        except httpx.HTTPStatusError as e:
            console.print(f"[red]Error creating conversation: {e.response.status_code}[/red]")
            if e.response.status_code == 401:
                console.print("[yellow]Try running 'az login' to authenticate.[/yellow]")
            raise typer.Exit(1)
        except httpx.ConnectError:
            console.print(f"[red]Could not connect to API at {base_url}[/red]")
            console.print("[yellow]Make sure the API server is running.[/yellow]")
            raise typer.Exit(1)

        # Send message with streaming
        console.print()
        response_text = ""
        tool_calls_displayed: set[str] = set()

        with Live(
            Spinner("dots", text="Thinking..."),
            refresh_per_second=10,
            console=console,
        ) as live:
            try:
                async with client.stream(
                    "POST",
                    f"{base_url}/conversations/{conv_id}/messages",
                    headers=headers,
                    json={"content": query, "stream": True},
                    timeout=120.0,
                ) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                            except json.JSONDecodeError:
                                continue

                            if data.get("type") == "token":
                                response_text += data.get("content", "")
                                live.update(Markdown(response_text))

                            elif data.get("type") == "tool_call":
                                tool_call = data.get("tool_call", {})
                                tool_name = tool_call.get("name", "unknown")
                                if tool_name not in tool_calls_displayed:
                                    tool_calls_displayed.add(tool_name)
                                    live.update(
                                        Panel(
                                            f"Using tool: [bold]{tool_name}[/bold]",
                                            title="Tool",
                                            border_style="yellow",
                                        )
                                    )

                            elif data.get("type") == "complete":
                                live.update(Markdown(response_text))

                            elif data.get("type") == "error":
                                console.print(
                                    f"[red]Error: {data.get('message', 'Unknown error')}[/red]"
                                )
                                raise typer.Exit(1)

            except httpx.HTTPStatusError as e:
                console.print(f"[red]Error sending message: {e.response.status_code}[/red]")
                raise typer.Exit(1)

        console.print()


async def _interactive_chat(
    subscription: str | None,
    base_url: str,
) -> None:
    """Run interactive chat mode."""
    console.print(
        Panel(
            "[bold]Welcome to Infra-Aware RAG CLI[/bold]\n\n"
            "Ask questions about your Azure infrastructure.\n"
            "Type [bold cyan]exit[/bold cyan], [bold cyan]quit[/bold cyan], "
            "or [bold cyan]q[/bold cyan] to end the session.\n"
            "Type [bold cyan]new[/bold cyan] to start a new conversation.",
            title="Interactive Mode",
            border_style="blue",
        )
    )

    token = await get_token()
    headers = get_headers(token)

    async with httpx.AsyncClient(timeout=120.0) as client:
        conv_id: str | None = None

        while True:
            console.print()

            try:
                query = console.input("[bold blue]You:[/bold blue] ")
            except (EOFError, KeyboardInterrupt):
                console.print("\nGoodbye!")
                break

            # Handle special commands
            if query.lower() in ("exit", "quit", "q"):
                console.print("Goodbye!")
                break

            if query.lower() == "new":
                conv_id = None
                console.print("[dim]Starting new conversation...[/dim]")
                continue

            if not query.strip():
                continue

            # Create conversation if needed
            if not conv_id:
                try:
                    metadata: dict[str, Any] = {}
                    if subscription:
                        metadata["subscription"] = subscription

                    conv_resp = await client.post(
                        f"{base_url}/conversations",
                        headers=headers,
                        json={"metadata": metadata} if metadata else None,
                    )
                    conv_resp.raise_for_status()
                    conv_id = conv_resp.json()["id"]
                except httpx.HTTPStatusError as e:
                    console.print(
                        f"[red]Error creating conversation: {e.response.status_code}[/red]"
                    )
                    if e.response.status_code == 401:
                        console.print("[yellow]Try running 'az login' to authenticate.[/yellow]")
                    continue
                except httpx.ConnectError:
                    console.print(f"[red]Could not connect to API at {base_url}[/red]")
                    continue

            # Send message
            console.print()
            console.print("[bold purple]Assistant:[/bold purple]")

            response_text = ""

            try:
                async with client.stream(
                    "POST",
                    f"{base_url}/conversations/{conv_id}/messages",
                    headers=headers,
                    json={"content": query, "stream": True},
                    timeout=120.0,
                ) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                            except json.JSONDecodeError:
                                continue

                            if data.get("type") == "token":
                                content = data.get("content", "")
                                console.print(content, end="")
                                response_text += content

                            elif data.get("type") == "tool_call":
                                tool_call = data.get("tool_call", {})
                                tool_name = tool_call.get("name", "unknown")
                                console.print(
                                    f"\n[yellow]-> Using: {tool_name}[/yellow]",
                                    end="",
                                )

                            elif data.get("type") == "complete":
                                console.print()  # Newline

                            elif data.get("type") == "error":
                                console.print(
                                    f"\n[red]Error: {data.get('message', 'Unknown error')}[/red]"
                                )

            except httpx.HTTPStatusError as e:
                console.print(f"\n[red]Error: {e.response.status_code}[/red]")
            except httpx.ConnectError:
                console.print(f"\n[red]Connection lost[/red]")


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    doc_type: str = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by document type (azure_resource, terraform_resource, git_commit, terraform_plan)",
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        "-n",
        help="Maximum number of results to return",
    ),
    mode: str = typer.Option(
        "hybrid",
        "--mode",
        "-m",
        help="Search mode: vector, keyword, or hybrid",
    ),
    api_url: str = typer.Option(
        None,
        "--api-url",
        "-u",
        help="API base URL",
        envvar="INFRA_RAG_API_URL",
    ),
) -> None:
    """Search infrastructure without starting a conversation.

    Examples:
        infra-rag search "storage accounts"
        infra-rag search -t azure_resource "virtual machines"
        infra-rag search -n 20 --mode vector "network security"
    """
    base_url = api_url or get_api_base_url()
    asyncio.run(_search(query, doc_type, limit, mode, base_url))


async def _search(
    query: str,
    doc_type: str | None,
    limit: int,
    mode: str,
    base_url: str,
) -> None:
    """Execute a direct search."""
    token = await get_token()
    headers = get_headers(token)

    body: dict[str, Any] = {
        "query": query,
        "top": limit,
        "mode": mode,
    }
    if doc_type:
        body["doc_types"] = [doc_type]

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                f"{base_url}/search",
                headers=headers,
                json=body,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            console.print(f"[red]Search failed: {e.response.status_code}[/red]")
            raise typer.Exit(1)
        except httpx.ConnectError:
            console.print(f"[red]Could not connect to API at {base_url}[/red]")
            raise typer.Exit(1)

    total = data.get("total_count", 0)
    results = data.get("results", [])

    console.print()
    console.print(f"[bold]Found {total} results:[/bold]")
    console.print()

    if not results:
        console.print("[dim]No results found.[/dim]")
        return

    for i, result in enumerate(results, 1):
        content = result.get("content", "")
        # Truncate long content
        if len(content) > 500:
            content = content[:500] + "..."

        doc_type_str = result.get("doc_type", "unknown")
        score = result.get("score", 0)

        # Get metadata for additional info
        metadata = result.get("metadata", {})
        resource_id = metadata.get("resource_id", "")
        address = metadata.get("address", "")

        title_parts = [f"[{i}] {doc_type_str}"]
        if score:
            title_parts.append(f"Score: {score:.3f}")

        subtitle = resource_id or address or result.get("id", "")

        panel_title = " | ".join(title_parts)

        console.print(
            Panel(
                content,
                title=panel_title,
                subtitle=subtitle[:80] if subtitle else None,
                border_style="green",
            )
        )


@app.command("query")
def resource_graph_query(
    kql: str = typer.Argument(..., help="Kusto query for Azure Resource Graph"),
    subscriptions: list[str] = typer.Option(
        None,
        "--subscription",
        "-s",
        help="Subscription IDs to query (can be specified multiple times)",
    ),
    output_format: str = typer.Option(
        "table",
        "--output",
        "-o",
        help="Output format: table, json, or raw",
    ),
    api_url: str = typer.Option(
        None,
        "--api-url",
        "-u",
        help="API base URL",
        envvar="INFRA_RAG_API_URL",
    ),
) -> None:
    """Execute a raw Azure Resource Graph query.

    Examples:
        infra-rag query "Resources | limit 10"
        infra-rag query "Resources | where type == 'microsoft.compute/virtualmachines'"
        infra-rag query -o json "Resources | summarize count() by type"
    """
    base_url = api_url or get_api_base_url()
    asyncio.run(_resource_graph_query(kql, subscriptions, output_format, base_url))


async def _resource_graph_query(
    kql: str,
    subscriptions: list[str] | None,
    output_format: str,
    base_url: str,
) -> None:
    """Execute Resource Graph query."""
    token = await get_token()
    headers = get_headers(token)

    body: dict[str, Any] = {"query": kql}
    if subscriptions:
        body["subscriptions"] = subscriptions

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                f"{base_url}/resources/resource-graph/query",
                headers=headers,
                json=body,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            console.print(f"[red]Query failed: {e.response.status_code}[/red]")
            try:
                error_detail = e.response.json().get("detail", "Unknown error")
                console.print(f"[red]{error_detail}[/red]")
            except Exception:
                pass
            raise typer.Exit(1)
        except httpx.ConnectError:
            console.print(f"[red]Could not connect to API at {base_url}[/red]")
            raise typer.Exit(1)

    results = data.get("results", [])
    total = data.get("total_records", len(results))

    if output_format == "json":
        # Output raw JSON
        console.print(json.dumps(results, indent=2))
        return

    if output_format == "raw":
        # Output minimal format
        for row in results:
            console.print(row)
        return

    # Table output
    console.print()

    if not results:
        console.print("[dim]No results found.[/dim]")
        return

    # Build table from results
    table = Table(show_header=True, header_style="bold cyan")

    # Get columns from first result
    if results:
        columns = list(results[0].keys())
        for col in columns:
            table.add_column(col)

        # Add rows (limit display to 50)
        display_results = results[:50]
        for row in display_results:
            values = []
            for col in columns:
                val = row.get(col, "")
                # Truncate long values
                str_val = str(val) if val is not None else ""
                if len(str_val) > 50:
                    str_val = str_val[:47] + "..."
                values.append(str_val)
            table.add_row(*values)

        console.print(table)

        if len(results) > 50:
            console.print(f"\n[dim]Showing 50 of {total} results[/dim]")
        else:
            console.print(f"\n[dim]{total} result(s)[/dim]")


@app.command()
def version() -> None:
    """Show version information."""
    console.print("[bold]Infra-Aware RAG CLI[/bold]")
    console.print("Version: 0.1.0")
    console.print()
    console.print(f"API URL: {get_api_base_url()}")


@app.command()
def config() -> None:
    """Show current configuration."""
    console.print("[bold]Current Configuration[/bold]")
    console.print()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Setting")
    table.add_column("Value")
    table.add_column("Source")

    api_url = os.getenv("INFRA_RAG_API_URL")
    table.add_row(
        "API URL",
        api_url or DEFAULT_API_BASE_URL,
        "env" if api_url else "default",
    )

    # Check Azure CLI status
    try:
        result = subprocess.run(
            ["az", "account", "show", "--query", "name", "-o", "tsv"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            account = result.stdout.strip()
            table.add_row("Azure Account", account, "az cli")
        else:
            table.add_row("Azure Account", "[yellow]Not logged in[/yellow]", "az cli")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        table.add_row("Azure Account", "[red]CLI not available[/red]", "-")

    console.print(table)


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
