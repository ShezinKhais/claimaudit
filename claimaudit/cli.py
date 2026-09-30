"""ClaimAudit CLI - audit research claims via Semantic Scholar."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from claimaudit.classifier import ClaimClassifier
from claimaudit.reporter import render_html, render_text, render_json
from claimaudit.scholar import ScholarError

# Windows consoles often default to cp1252, which mangles the arrows and other
# non-ASCII characters in the output; force UTF-8 where the stream supports it.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

app     = typer.Typer(name="claimaudit", add_completion=False)
console = Console()


@app.command("audit")
def audit(
    topic: str = typer.Argument(..., help="Research topic to audit"),
    n_papers: int     = typer.Option(10,   "--papers",    "-n"),
    from_year: int    = typer.Option(2000, "--from-year", "-f"),
    to_year: int      = typer.Option(2025, "--to-year",   "-t"),
    min_citations: int= typer.Option(5,    "--min-cites"),
    html_out: Path    = typer.Option(None, "--html"),
    json_out: Path    = typer.Option(None, "--json"),
    api_key: str      = typer.Option("",   "--api-key", envvar="SEMANTIC_SCHOLAR_API_KEY"),
    demo: bool        = typer.Option(False, "--demo",
                                     help="Use bundled sample data (no network or API key)"),
):
    """Audit scientific claims in papers about a topic."""
    if demo:
        console.print("[dim]Demo mode: using bundled sample data, not live results.[/dim]")
    console.print(f"[bold]Auditing:[/bold] {topic!r} - fetching up to {n_papers} papers...")

    clf = ClaimClassifier(api_key=api_key, min_citations=min_citations, demo=demo)
    try:
        results = clf.audit_topic(topic, n_papers, from_year, to_year)
    except ScholarError as e:
        console.print(f"[red]Semantic Scholar is unavailable:[/red] {e}")
        console.print("[yellow]Tip:[/yellow] rerun with [bold]--demo[/bold] to try the tool offline.")
        raise typer.Exit(code=1)

    if not results:
        console.print("[yellow]No auditable claims found.[/yellow]")
        raise typer.Exit()

    table = Table(title=f"ClaimAudit: {topic}")
    table.add_column("Score", justify="right")
    table.add_column("Verdict")
    table.add_column("Paper")
    table.add_column("Claim (truncated)")
    for r in results:
        s = r.survival
        table.add_row(
            f"{s.score}/10",
            s.verdict,
            r.paper.title[:50],
            s.claim_text[:60] + "...",
        )
    console.print(table)

    if html_out:
        # The report states its own subject and whether it came from sample
        # data, so both have to travel with the results.
        render_html(results, topic=topic, demo=demo, output_path=html_out)
        console.print(f"HTML -> {html_out}")
    if json_out:
        json_out.write_text(render_json(results))
        console.print(f"JSON -> {json_out}")


if __name__ == "__main__":
    app()
