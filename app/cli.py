"""Command-line interface for the AI orchestration framework."""
import asyncio
from datetime import datetime
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from .planner import Planner
from .executor import DAGExecutor
from .config import Config


console = Console()

# Prompt log file
PROMPT_LOG_FILE = Path(__file__).parent.parent / "prompts.log"


def log_prompt(model: str, prompt: str):
    """Log user prompt to file."""
    try:
        timestamp = datetime.now().isoformat()
        log_entry = f"{timestamp}|{model}|{prompt}\n"
        
        with open(PROMPT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        # Don't fail if logging fails
        console.print(f"[dim red]Warning: Failed to log prompt: {e}[/dim red]")


def select_from_list(items: list, prompt_text: str, default_index: int = 0, item_formatter=None) -> str:
    """Display numbered list and allow selection by number or name.
    
    Args:
        items: List of items to select from
        prompt_text: Text to display as prompt
        default_index: Index of default item (0-based)
        item_formatter: Optional function(item, index) -> str to format each item display
    """
    if not items:
        raise ValueError("Cannot select from empty list")
    
    if len(items) == 1:
        return items[0]
    
    # Display numbered list
    console.print(f"\n[bold]{prompt_text}:[/bold]")
    for i, item in enumerate(items, 1):
        marker = "[green]→[/green]" if i == default_index + 1 else " "
        if item_formatter:
            display_text = item_formatter(item, i - 1)
        else:
            display_text = str(item)
        console.print(f"  {marker} [{i}] {display_text}")
    
    # Get user input
    while True:
        choice = Prompt.ask(f"\nEnter choice [1-{len(items)}] or name", default=str(default_index + 1))
        
        # Try to parse as number
        try:
            choice_num = int(choice)
            if 1 <= choice_num <= len(items):
                return items[choice_num - 1]
            else:
                console.print(f"[red]Invalid number. Please enter 1-{len(items)}[/red]")
                continue
        except ValueError:
            # Not a number, try to match by name
            if choice in items:
                return choice
            else:
                console.print(f"[red]Invalid choice. Please enter a number (1-{len(items)}) or provider name[/red]")
                continue


def print_dag(plan):
    """Print DAG structure in text format."""
    console.print("\n[bold cyan]Execution Plan DAG:[/bold cyan]")
    
    # Print nodes
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Node ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Provider", style="yellow")
    table.add_column("Dependencies", style="blue")
    
    for node in plan.nodes:
        deps = ", ".join(node.dependencies) if node.dependencies else "none"
        table.add_row(node.id, node.name, f"{node.provider}/{node.model}", deps)
    
    console.print(table)
    
    # Print edges
    if plan.edges:
        console.print("\n[bold cyan]Edges (Dependencies):[/bold cyan]")
        for edge in plan.edges:
            console.print(f"  {edge['from']} -> {edge['to']}")
    else:
        # Infer edges from dependencies
        console.print("\n[bold cyan]Edges (from dependencies):[/bold cyan]")
        for node in plan.nodes:
            for dep_id in node.dependencies:
                console.print(f"  {dep_id} -> {node.id}")


def print_node_details(plan):
    """Print detailed information about each node."""
    console.print("\n[bold cyan]Node Details:[/bold cyan]")
    
    for node in plan.nodes:
        input_info = node.input_description if node.input_description else "No inputs needed"
        output_info = node.output_description if node.output_description else "See description"
        
        panel_content = f"""
[bold]Description:[/bold] {node.description}

[bold]Inputs Needed:[/bold] {input_info}

[bold]Outputs Produced:[/bold] {output_info}
"""
        console.print(Panel(panel_content, title=f"[bold]{node.id}: {node.name}[/bold]", border_style="blue"))


def print_execution_status(plan):
    """Print current execution status of nodes."""
    console.print("\n[bold cyan]Execution Status:[/bold cyan]")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Node ID", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Time", style="yellow")
    table.add_column("Error", style="red")
    
    for node in plan.nodes:
        status_style = {
            "pending": "dim",
            "ready": "yellow",
            "running": "blue",
            "completed": "green",
            "failed": "red"
        }.get(node.status, "white")
        
        time_str = f"{node.execution_time:.2f}s" if node.execution_time else "-"
        error_str = node.error[:50] + "..." if node.error and len(node.error) > 50 else (node.error or "-")
        
        table.add_row(
            node.id,
            f"[{status_style}]{node.status}[/{status_style}]",
            time_str,
            error_str
        )
    
    console.print(table)


def print_results(execution_result):
    """Print execution results."""
    console.print("\n[bold green]Execution Results:[/bold green]")
    
    for node_id, result in execution_result.get("node_results", {}).items():
        # Result is now natural language, not JSON
        result_text = result if isinstance(result, str) else str(result)
        console.print(Panel(result_text, title=f"[bold]Node {node_id} Result[/bold]", border_style="green"))


async def main():
    """Main CLI loop."""
    console.print("[bold magenta]AI Agent Orchestration Framework[/bold magenta]")
    console.print("=" * 60)
    
    # Check available providers
    available = Config.get_available_providers()
    available_providers = [p for p, avail in available.items() if avail]
    
    if not available_providers:
        console.print("[red]ERROR: No AI providers configured. Please set API keys in .env file.[/red]")
        return
    
    # Select planner provider with model names
    if len(available_providers) == 1:
        planner_provider = available_providers[0]
        default_model = Config.DEFAULT_MODELS.get(planner_provider, "default")
        console.print(f"\n[green]Using {planner_provider} (model: {default_model}) as planner provider.[/green]")
    else:
        # Format function to show provider name with default model
        def format_provider(provider: str, index: int) -> str:
            default_model = Config.DEFAULT_MODELS.get(provider, "default")
            return f"{provider} (model: {default_model})"
        
        planner_provider = select_from_list(
            available_providers,
            "Select planner provider",
            default_index=0,
            item_formatter=format_provider
        )
        default_model = Config.DEFAULT_MODELS.get(planner_provider, "default")
        console.print(f"\n[green]Selected: {planner_provider} (model: {default_model})[/green]")
    
    planner = Planner(provider_name=planner_provider, model=default_model)
    
    while True:
        console.print("\n" + "=" * 60)
        
        # Get user prompt
        user_prompt = Prompt.ask("\n[bold]Enter your task[/bold] (or 'quit' to exit)")
        
        if user_prompt.lower() in ['quit', 'exit', 'q']:
            console.print("[yellow]Goodbye![/yellow]")
            break
        
        # Log the prompt
        log_prompt(planner_provider, user_prompt)
        
        try:
            # Create plan - force all nodes to use the same provider/model
            console.print("\n[bold yellow]Creating execution plan...[/bold yellow]")
            console.print(f"[dim]All nodes will use: {planner_provider} / {default_model}[/dim]")
            plan = await planner.create_plan(
                user_prompt,
                force_provider=planner_provider,
                force_model=default_model
            )
            
            # Display plan
            print_dag(plan)
            
            # Ask for details
            if Confirm.ask("\nShow detailed node information?"):
                print_node_details(plan)
            
            # Confirm execution
            if not Confirm.ask("\n[bold]Execute this plan?[/bold]"):
                console.print("[yellow]Plan execution cancelled.[/yellow]")
                continue
            
            # Execute
            console.print("\n[bold yellow]Executing plan...[/bold yellow]")
            executor = DAGExecutor()
            execution_result = await executor.execute(plan)
            
            # Show status
            print_execution_status(plan)
            
            # Show results
            if Confirm.ask("\nShow execution results?"):
                print_results(execution_result)
            
            # Show logs
            if Confirm.ask("\nShow execution logs?"):
                console.print("\n[bold cyan]Execution Logs:[/bold cyan]")
                for log in execution_result.get("execution_logs", []):
                    console.print(f"  {log}")
        
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted by user.[/yellow]")
            break
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
            import traceback
            console.print(traceback.format_exc())


if __name__ == "__main__":
    asyncio.run(main())
