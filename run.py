import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

from langchain_core.messages import HumanMessage, ToolMessage
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from src.agent.graph import build_guardrailed_graph, get_async_checkpointer

console = Console()


async def run_single_query(graph, query: str, config: dict, auto_approve: bool = False):
    console.print(f"[bold cyan]User Query:[/bold cyan] {query}")
    state = {
        "messages": [HumanMessage(content=query)],
        "guardrail_response": None,
        "is_blocked": False,
        "context": {},
    }

    result = await graph.ainvoke(state, config=config)

    # Human-in-the-Loop breakpoint check
    snapshot = await graph.aget_state(config)
    while snapshot.next and "tools" in snapshot.next:
        last_msg = snapshot.values["messages"][-1]
        tool_calls = getattr(last_msg, "tool_calls", [])

        for tc in tool_calls:
            console.print(
                f"  [cyan]⚡ [TOOL REQUESTED][/cyan] [bold]{tc['name']}[/bold] | args={tc.get('args', {})}"
            )

        code_call = next((tc for tc in tool_calls if tc["name"] == "execute_python_code"), None)

        if code_call and not auto_approve:
            code_text = code_call.get("args", {}).get("code", "")
            console.print(
                Panel(
                    code_text,
                    title="[bold yellow]⚠️  [APPROVAL REQUIRED] Python Code[/bold yellow]",
                    border_style="yellow",
                )
            )
            choice = Prompt.ask("Run this code?", choices=["y", "n"], default="y")

            if choice.lower() != "y":
                console.print("[red]❌ Execution cancelled by user.[/red]")
                rejection_msg = ToolMessage(
                    content="Execution cancelled by user. Do not re-attempt this script.",
                    tool_call_id=code_call["id"],
                    name=code_call["name"],
                )
                await graph.aupdate_state(config, {"messages": [rejection_msg]}, as_node="tools")
                result = await graph.ainvoke(None, config=config)
                snapshot = await graph.aget_state(config)
                continue

        result = await graph.ainvoke(None, config=config)
        snapshot = await graph.aget_state(config)

    for msg in result.get("messages", []):
        if isinstance(msg, ToolMessage):
            summary = (
                str(msg.content)[:120] + "..." if len(str(msg.content)) > 120 else str(msg.content)
            )
            console.print(f"  [green]✓ [TOOL COMPLETED][/green] {summary}")

    output = result.get("guardrail_response")
    if not output and result.get("messages"):
        last_m = result["messages"][-1]
        output = last_m.content if hasattr(last_m, "content") else str(last_m)

    is_blocked = result.get("is_blocked", False)
    border_style = "red" if is_blocked else "green"
    status_tag = "[BLOCKED BY GUARDRAIL]" if is_blocked else "[PASSED & EXECUTED]"

    console.print(
        Panel(
            output or "No response generated.",
            title=f"{status_tag} Assistant Output",
            border_style=border_style,
        )
    )
    return result


async def main():
    default_thread = os.getenv("DEFAULT_THREAD_ID", "main-session")
    auto_approve_env = os.getenv("AUTO_APPROVE_CODE_EXECUTION", "false").lower() == "true"

    parser = argparse.ArgumentParser(description="Local ReAct agent CLI")
    parser.add_argument("-q", "--query", type=str, help="Single query to run non-interactively")
    parser.add_argument(
        "-t",
        "--thread",
        type=str,
        default=default_thread,
        help="Conversation thread ID",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        default=auto_approve_env,
        help="Skip interactive confirmation for code runs",
    )
    args = parser.parse_args()

    console.print("[bold yellow]Starting agent...[/bold yellow]")

    async with get_async_checkpointer() as checkpointer:
        graph = build_guardrailed_graph(
            "config/rails", checkpointer=checkpointer, interrupt_tools=True
        )
        console.print(f"[bold green]Connected! (Thread: '{args.thread}')[/bold green]\n")

        config = {"configurable": {"thread_id": args.thread}}

        if args.query:
            await run_single_query(graph, args.query, config=config, auto_approve=args.auto_approve)
            return

        console.print("[dim]Commands: '/thread <name>', '/history', or 'exit'[/dim]")
        active_thread = args.thread

        while True:
            try:
                user_input = input(f"\nYou [{active_thread}] > ").strip()
                if not user_input or user_input.lower() in ("exit", "quit"):
                    break

                if user_input.startswith("/thread "):
                    new_thread = user_input.split(maxsplit=1)[1].strip()
                    if new_thread:
                        active_thread = new_thread
                        config = {"configurable": {"thread_id": active_thread}}
                        console.print(f"[cyan]Switched to thread: '{active_thread}'[/cyan]")
                        continue

                if user_input.lower() == "/history":
                    snapshot = await graph.aget_state(config)
                    history_messages = (
                        snapshot.values.get("messages", []) if snapshot.values else []
                    )
                    console.print(
                        f"[cyan]History in thread '{active_thread}' ({len(history_messages)} turns):[/cyan]"
                    )
                    for idx, m in enumerate(history_messages, start=1):
                        role = type(m).__name__
                        snippet = (
                            str(m.content)[:100] + "..."
                            if len(str(m.content)) > 100
                            else str(m.content)
                        )
                        console.print(f"  {idx}. [bold]{role}[/bold]: {snippet}")
                    continue

                await run_single_query(
                    graph, user_input, config=config, auto_approve=args.auto_approve
                )

            except (KeyboardInterrupt, EOFError):
                break

        console.print("\n[dim]Bye.[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
