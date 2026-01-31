#!/usr/bin/env python3
"""Standalone test tool for AI providers."""
import asyncio
import sys

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    # Fallback to basic print
    class Console:
        def print(self, *args, **kwargs):
            print(*args)

try:
    from backend.config import Config
    from backend.providers.factory import create_provider
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure you're running from the project root and dependencies are installed.")
    sys.exit(1)

console = Console() if HAS_RICH else Console()

TEST_QUESTION = "What is the capital of China? Answer in one sentence."


async def test_provider(provider_name: str) -> dict:
    """Test a single provider."""
    result = {
        "provider": provider_name,
        "status": "unknown",
        "response": None,
        "error": None,
        "time": None
    }
    
    try:
        import time
        start_time = time.time()
        
        provider = create_provider(provider_name)
        model = Config.DEFAULT_MODELS.get(provider_name, "default")
        
        console.print(f"[yellow]Testing {provider_name} with model {model}...[/yellow]")
        
        # Test with a simple prompt first
        response = await provider.generate(
            prompt=TEST_QUESTION,
            model=model,
            system_prompt=None
        )
        
        elapsed = time.time() - start_time
        result["status"] = "success"
        result["response"] = response
        result["time"] = elapsed
        
        console.print(f"[green]✓ {provider_name} succeeded ({elapsed:.2f}s)[/green]")
        
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        import traceback
        result["traceback"] = traceback.format_exc()
        
        # Print detailed error info
        console.print(f"[red]✗ {provider_name} failed[/red]")
        console.print(f"[dim red]Error: {e}[/dim red]")
        if HAS_RICH:
            console.print(Panel(
                result["traceback"],
                title=f"[bold red]{provider_name} Error Details[/bold red]",
                border_style="red"
            ))
        else:
            console.print(f"Traceback:\n{result['traceback']}")
    
    return result


async def main():
    """Test all available providers."""
    console.print("[bold magenta]AI Provider Test Tool[/bold magenta]")
    console.print("=" * 60)
    
    # Check available providers
    try:
        available = Config.get_available_providers()
        available_providers = [name for name, is_avail in available.items() if is_avail]
    except Exception as e:
        console.print(f"[red]Error checking providers: {e}[/red]")
        console.print("[yellow]Make sure .env file exists and is readable, or set environment variables.[/yellow]")
        return 1
    
    if not available_providers:
        console.print("[red]No providers configured. Please set API keys in .env file.[/red]")
        console.print("[dim]Configured providers status:[/dim]")
        all_providers = Config.get_available_providers()
        for name, is_avail in all_providers.items():
            status = "[green]✓[/green]" if is_avail else "[red]✗[/red]"
            console.print(f"  {status} {name}")
        return 1
    
    console.print(f"\n[bold]Testing {len(available_providers)} provider(s):[/bold] {', '.join(available_providers)}")
    console.print(f"[dim]Test question: {TEST_QUESTION}[/dim]\n")
    
    # Test all providers
    results = []
    for provider_name in available_providers:
        result = await test_provider(provider_name)
        results.append(result)
        console.print()  # Empty line between tests
    
    # Display results table
    console.print("\n[bold cyan]Test Results:[/bold cyan]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Provider", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Time", style="yellow")
    table.add_column("Response Preview", style="white", max_width=50)
    table.add_column("Error", style="red", max_width=40)
    
    for result in results:
        status_style = "green" if result["status"] == "success" else "red"
        status_text = "✓ PASS" if result["status"] == "success" else "✗ FAIL"
        
        time_str = f"{result['time']:.2f}s" if result["time"] else "-"
        
        response_preview = "-"
        if result["response"]:
            preview = result["response"][:47] + "..." if len(result["response"]) > 50 else result["response"]
            response_preview = preview.replace("\n", " ")
        
        error_str = result["error"][:37] + "..." if result["error"] and len(result["error"]) > 40 else (result["error"] or "-")
        
        table.add_row(
            result["provider"],
            f"[{status_style}]{status_text}[/{status_style}]",
            time_str,
            response_preview,
            error_str
        )
    
    console.print(table)
    
    # Display detailed responses
    console.print("\n[bold cyan]Detailed Responses:[/bold cyan]")
    for result in results:
        if result["status"] == "success":
            panel_content = result["response"]
            console.print(Panel(panel_content, title=f"[bold green]{result['provider']} Response[/bold green]", border_style="green"))
        else:
            panel_content = f"Error: {result['error']}\n\nTraceback:\n{result.get('traceback', 'N/A')}"
            console.print(Panel(panel_content, title=f"[bold red]{result['provider']} Error[/bold red]", border_style="red"))
        console.print()
    
    # Summary
    passed = sum(1 for r in results if r["status"] == "success")
    failed = len(results) - passed
    
    console.print(f"\n[bold]Summary:[/bold] {passed} passed, {failed} failed out of {len(results)} providers")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
