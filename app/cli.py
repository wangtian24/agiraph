"""Command-line interface for the AI orchestration framework."""
import asyncio
import json
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from .planner import Planner
from .executor import DAGExecutor
from .config import Config


console = Console()


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
        panel_content = f"""
[bold]Description:[/bold] {node.description}

[bold]Input Contract:[/bold]
{json.dumps(node.input_contract, indent=2)}

[bold]Output Contract:[/bold]
{json.dumps(node.output_contract, indent=2)}
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
        panel_content = json.dumps(result, indent=2)
        console.print(Panel(panel_content, title=f"[bold]Node {node_id} Result[/bold]", border_style="green"))


async def main():
    """Main CLI loop."""
    console.print("[bold magenta]AI Agent Orchestration Framework[/bold magenta]")
    console.print("=" * 60)
    
    # Check available providers
    available = Config.get_available_providers()
    console.print("\n[bold]Available AI Providers:[/bold]")
    for provider, is_available in available.items():
        status = "[green]✓[/green]" if is_available else "[red]✗[/red]"
        console.print(f"  {status} {provider}")
    
    if not any(available.values()):
        console.print("[red]ERROR: No AI providers configured. Please set API keys in .env file.[/red]")
        return
    
    # Select planner provider
    available_providers = [p for p, avail in available.items() if avail]
    if len(available_providers) == 1:
        planner_provider = available_providers[0]
        console.print(f"\n[green]Using {planner_provider} as planner provider.[/green]")
    else:
        planner_provider = Prompt.ask(
            "\nSelect planner provider",
            choices=available_providers,
            default=available_providers[0]
        )
    
    planner = Planner(provider_name=planner_provider)
    
    while True:
        console.print("\n" + "=" * 60)
        
        # Get user prompt
        user_prompt = Prompt.ask("\n[bold]Enter your task[/bold] (or 'quit' to exit)")
        
        if user_prompt.lower() in ['quit', 'exit', 'q']:
            console.print("[yellow]Goodbye![/yellow]")
            break
        
        try:
            # Create plan
            console.print("\n[bold yellow]Creating execution plan...[/bold yellow]")
            plan = await planner.create_plan(user_prompt)
            
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
