"""
Builds a Neo4j knowledge graph from an Obsidian vault using wikilinks only.

Usage:
    python build_knowledge_graph.py --vault /path/to/vault
    python build_knowledge_graph.py --vault /path/to/vault --dry-run
    python build_knowledge_graph.py --vault /path/to/vault --clear
"""
 
import sys
import argparse
from pathlib import Path
 
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TaskProgressColumn, TextColumn, BarColumn
from rich.table import Table
 
from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, BATCH_SIZE
from models import Note
from parser import scan_vault as _scan_vault_pure, resolve_backlinks
from graph import GraphBuilder
 
console = Console()
 
 
# ===============================================================================
# VAULT SCANNING
# ===============================================================================
 
def scan_vault(vault_root: Path) -> list[Note]:
    all_md = list(vault_root.rglob("*.md"))
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]Scanning vault…[/]"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("parse", total=len(all_md))
        notes, errors, skipped = _scan_vault_pure(vault_root)
        progress.update(task, completed=len(all_md))
 
    if skipped:
        console.print(f"[dim]Skipped {skipped} files in ignored folders.[/]")
    if errors:
        console.print(f"[yellow]⚠  {len(errors)} parse errors:[/]")
        for e in errors[:5]:
            console.print(f"   {e}")
    return notes
 
 
# ===============================================================================
# REPORTING
# ===============================================================================
 
def print_summary(notes: list[Note], stats: dict | None = None):
    type_counts: dict[str, int] = {}
    total_links    = 0
    tag_link_count = 0
    for n in notes:
        type_counts[n.note_type] = type_counts.get(n.note_type, 0) + 1
        total_links    += len(n.links)
        tag_link_count += sum(1 for l in n.links if l.is_tag_link)
    t = Table(title="Vault Scan Results", header_style="bold cyan")
    t.add_column("Note Type",  style="cyan")
    t.add_column("Count",      justify="right")
    t.add_column("% of Vault", justify="right")
    for ntype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        t.add_row(ntype, str(count), f"{100 * count / len(notes):.1f}%")
    t.add_row("[bold]TOTAL[/]", f"[bold]{len(notes)}[/]", "[bold]100%[/]")
    console.print(t)
    console.print(f"\n[cyan]Total links:[/]      {total_links}")
    console.print(f"  TAGGED_WITH:     {tag_link_count}")
    console.print(f"  Body wikilinks:  {total_links - tag_link_count}")
    top = sorted(notes, key=lambda n: len(n.backlinks), reverse=True)[:10]
    if any(n.backlinks for n in top):
        t2 = Table(title="Top 10 Most-Referenced Notes", header_style="bold magenta")
        t2.add_column("Title",     style="magenta")
        t2.add_column("Type",      style="cyan")
        t2.add_column("Backlinks", justify="right")
        t2.add_column("Subfolder")
        for n in top:
            if n.backlinks:
                t2.add_row(n.title, n.note_type, str(len(n.backlinks)), n.subfolder)
        console.print(t2)
    if not stats:
        console.print("\n[yellow]DRY RUN — nothing written to Neo4j.[/]")
        return
    console.print("\n[bold green]✓ Graph written to Neo4j[/]")
    console.print(f"  Nodes:          {stats['nodes']}")
    console.print(f"  Relationships:  {stats['relationships']}")
    console.print(f"  Isolated nodes: {stats['isolated_nodes']}")
    t3 = Table(title="Relationship Types", header_style="bold yellow")
    t3.add_column("Type",  style="yellow")
    t3.add_column("Count", justify="right")
    for row in stats["relationship_distribution"]:
        t3.add_row(row["rel"], str(row["c"]))
    console.print(t3)
    if stats["tag_hubs"]:
        t4 = Table(title="Top Tag Hubs", header_style="bold green")
        t4.add_column("Tag",            style="green")
        t4.add_column("Notes using it", justify="right")
        for row in stats["tag_hubs"]:
            if row["refs"]:
                t4.add_row(row["tag"], str(row["refs"]))
        console.print(t4)
 
 
# ===============================================================================
# MAIN
# ===============================================================================
 
def main():
    arg_parser = argparse.ArgumentParser(
        description="Build Neo4j knowledge graph from Obsidian vault"
    )
    arg_parser.add_argument("--vault",   required=True)
    arg_parser.add_argument("--dry-run", action="store_true")
    arg_parser.add_argument("--clear",   action="store_true")
    arg_parser.add_argument("--limit",   type=int, default=None)
    args = arg_parser.parse_args()

    vault_root = Path(args.vault).expanduser().resolve()
    if not vault_root.exists():
        console.print(f"[red]Vault not found:[/] {vault_root}")
        sys.exit(1)

    console.rule("[bold cyan]Obsidian → Neo4j Knowledge Graph Builder[/]")
    console.print(f"Vault: [cyan]{vault_root}[/]")
    console.print(f"Mode:  [cyan]{'DRY RUN' if args.dry_run else 'WRITE'}[/]\n")

    notes = scan_vault(vault_root)
    if args.limit:
        notes = notes[: args.limit]
        console.print(f"[yellow]Limited to {args.limit} notes.[/]")
    if not notes:
        console.print("[red]No notes found.[/]")
        sys.exit(1)

    console.print(f"\n[green]✓ Parsed {len(notes)} notes[/]")
    resolve_backlinks(notes)

    if args.dry_run:
        print_summary(notes)
        return
 
    console.print("\nConnecting to Neo4j…")
    db = GraphBuilder(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    if not db.verify_connection():
        sys.exit(1)
    console.print("[green]✓ Connected[/]")
 
    try:
        if args.clear:
            db.clear_graph()
        db.create_constraints()
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]Writing nodes…[/]"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("nodes", total=len(notes))
            for i in range(0, len(notes), BATCH_SIZE):
                db.upsert_notes(notes[i : i + BATCH_SIZE])
                progress.advance(task, BATCH_SIZE)
        console.print("Writing relationships…")
        db.upsert_relationships(notes)
        print_summary(notes, db.get_stats())
    finally:
        db.close()
 
 
if __name__ == "__main__":
    main()
 
 
 