"""Click CLI for skillm."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import Config, load_config
from .core import Library, Project
from .inject import inject as inject_skills
from .skillpack import export_skill, import_skillpack

console = Console()


def _get_library() -> Library:
    try:
        return Library()
    except Exception:
        console.print("[red]Library not initialized. Run 'skillm library init' first.[/red]")
        sys.exit(1)


def _get_project(library: Library | None = None) -> Project:
    project = Project(library=library or _get_library())
    if not project.skills_json.exists():
        console.print("[red]Project not initialized. Run 'skillm init' first.[/red]")
        sys.exit(1)
    return project


def _format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{size_bytes} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# ── Root ────────────────────────────────────────────────────

@click.group()
@click.version_option(__version__)
def cli():
    """skillm — Local-first skill manager for AI coding agents."""


# ── Library ─────────────────────────────────────────────────

@cli.group()
def library():
    """Manage the skill library."""


@library.command("init")
@click.option("--path", default=None, help="Library path (default: ~/.skillm)")
def library_init(path: str | None):
    """Initialize a new skill library."""
    config = Config()
    if path:
        config.library.path = path
    lib = Library(config)
    lib.init()
    console.print(f"[green]Library initialized at {lib.config.library_path}[/green]")


@library.command("stats")
def library_stats():
    """Show library statistics."""
    lib = _get_library()
    s = lib.stats()
    console.print(
        f"Skills: [bold]{s['skills']}[/bold] | "
        f"Versions: [bold]{s['versions']}[/bold] | "
        f"Size: [bold]{_format_size(s['total_size'])}[/bold] | "
        f"Backend: [bold]{s['backend']}[/bold]"
    )


@library.command("rebuild")
def library_rebuild():
    """Rebuild database from skill files on disk."""
    lib = _get_library()
    count = lib.rebuild()
    console.print(f"[green]Rebuilt database: {count} skill version(s) indexed.[/green]")


@library.command("compact")
def library_compact():
    """Compact the database (VACUUM)."""
    lib = _get_library()
    lib.db.vacuum()
    console.print("[green]Database compacted.[/green]")


@library.command("check")
def library_check():
    """Check library integrity."""
    lib = _get_library()
    disk_skills = dict(lib.backend.list_skill_dirs())
    db_skills = {s.name: [v.version for v in s.versions] for s in lib.list_skills()}

    issues = []
    for name, versions in disk_skills.items():
        if name not in db_skills:
            issues.append(f"On disk but not in DB: {name}")
        else:
            for v in versions:
                if v not in db_skills[name]:
                    issues.append(f"On disk but not in DB: {name}/{v}")

    for name, versions in db_skills.items():
        if name not in disk_skills:
            issues.append(f"In DB but not on disk: {name}")
        else:
            for v in versions:
                if v not in disk_skills[name]:
                    issues.append(f"In DB but not on disk: {name}/{v}")

    if issues:
        console.print(f"[yellow]Found {len(issues)} issue(s):[/yellow]")
        for issue in issues:
            console.print(f"  - {issue}")
        console.print("[dim]Run 'skillm library rebuild' to fix.[/dim]")
    else:
        console.print("[green]Library OK — DB matches disk.[/green]")


# ── Skill Operations ───────────────────────────────────────

@cli.command()
@click.argument("source", type=click.Path(exists=True))
@click.option("--name", default=None, help="Override skill name")
@click.option("--version", default=None, help="Explicit version (default: auto-increment)")
def publish(source: str, name: str | None, version: str | None):
    """Publish a skill directory to the library."""
    lib = _get_library()
    skill_name, ver = lib.publish(Path(source), name=name, version=version)
    console.print(f"[green]Published {skill_name}@{ver}[/green]")


@cli.command()
@click.argument("name")
@click.option("--version", default=None, help="Remove specific version only")
def remove(name: str, version: str | None):
    """Remove a skill from the library."""
    lib = _get_library()
    if lib.remove(name, version=version):
        target = f"{name}@{version}" if version else name
        console.print(f"[green]Removed {target}[/green]")
    else:
        console.print(f"[red]Skill '{name}' not found[/red]")


@cli.command()
@click.argument("name")
def info(name: str):
    """Show skill details."""
    lib = _get_library()
    skill = lib.info(name)
    if skill is None:
        console.print(f"[red]Skill '{name}' not found[/red]")
        return

    console.print(f"[bold]Name:[/bold] {skill.name}")
    console.print(f"[bold]Description:[/bold] {skill.description}")
    if skill.tags:
        console.print(f"[bold]Tags:[/bold] {', '.join(skill.tags)}")
    if skill.author:
        console.print(f"[bold]Author:[/bold] {skill.author}")
    if skill.source:
        console.print(f"[bold]Source:[/bold] {skill.source}")
    if skill.versions:
        ver_str = ", ".join(v.version for v in skill.versions)
        latest = skill.versions[-1].version
        console.print(f"[bold]Versions:[/bold] {ver_str} (latest: {latest})")
        total = sum(v.total_size for v in skill.versions)
        total_files = sum(v.file_count for v in skill.versions)
        console.print(f"[bold]Files:[/bold] {total_files} ({_format_size(total)})")


@cli.command("list")
def list_cmd():
    """List all skills in the library."""
    lib = _get_library()
    skills = lib.list_skills()

    if not skills:
        console.print("[dim]No skills in library.[/dim]")
        return

    table = Table(show_header=True)
    table.add_column("Name", style="bold")
    table.add_column("Latest")
    table.add_column("Tags")
    table.add_column("Size", justify="right")
    table.add_column("Updated")

    for skill in skills:
        latest = skill.versions[-1] if skill.versions else None
        table.add_row(
            skill.name,
            latest.version if latest else "-",
            ", ".join(skill.tags) if skill.tags else "",
            _format_size(latest.total_size) if latest else "-",
            skill.updated_at[:10] if skill.updated_at else "-",
        )

    console.print(table)


@cli.command()
@click.argument("name")
def versions(name: str):
    """List all versions of a skill."""
    lib = _get_library()
    skill = lib.info(name)
    if skill is None:
        console.print(f"[red]Skill '{name}' not found[/red]")
        return

    if not skill.versions:
        console.print("[dim]No versions.[/dim]")
        return

    table = Table(show_header=True)
    table.add_column("Version")
    table.add_column("Files", justify="right")
    table.add_column("Size", justify="right")
    table.add_column("Published")

    for v in skill.versions:
        latest_marker = " (latest)" if v == skill.versions[-1] else ""
        table.add_row(
            v.version + latest_marker,
            str(v.file_count),
            _format_size(v.total_size),
            v.published_at[:10] if v.published_at else "-",
        )

    console.print(table)


@cli.command()
@click.argument("query")
def search(query: str):
    """Search skills in the library."""
    lib = _get_library()
    results = lib.search(query)

    if not results:
        console.print("[dim]No results.[/dim]")
        return

    for skill in results:
        latest = skill.versions[-1] if skill.versions else None
        ver = f"@{latest.version}" if latest else ""
        tags = f" [{', '.join(skill.tags)}]" if skill.tags else ""
        console.print(f"[bold]{skill.name}[/bold]{ver}{tags}")
        if skill.description:
            console.print(f"  {skill.description}")


@cli.command()
@click.argument("name")
@click.argument("tags", nargs=-1, required=True)
def tag(name: str, tags: tuple[str]):
    """Add tags to a skill."""
    lib = _get_library()
    if lib.tag(name, list(tags)):
        console.print(f"[green]Tagged {name} with: {', '.join(tags)}[/green]")
    else:
        console.print(f"[red]Skill '{name}' not found[/red]")


@cli.command()
@click.argument("name")
@click.argument("tags", nargs=-1, required=True)
def untag(name: str, tags: tuple[str]):
    """Remove tags from a skill."""
    lib = _get_library()
    if lib.untag(name, list(tags)):
        console.print(f"[green]Untagged {name}: {', '.join(tags)}[/green]")
    else:
        console.print(f"[red]Skill '{name}' not found[/red]")


# ── Project Operations ─────────────────────────────────────

@cli.command("init")
def project_init():
    """Initialize current project for skill consumption."""
    lib = _get_library()
    project = Project(library=lib)
    project.init()
    console.print("[green]Project initialized — created skills.json and .skills/[/green]")


@cli.command()
@click.argument("name")
@click.option("--pin", is_flag=True, help="Pin to this version")
def add(name: str, pin: bool):
    """Add a skill from the library to this project."""
    # Parse name@version
    version = None
    if "@" in name:
        name, version = name.rsplit("@", 1)

    project = _get_project()
    ver = project.add(name, version=version, pin=pin)
    console.print(f"[green]Added {name}@{ver}[/green]")


@cli.command()
@click.argument("name")
def drop(name: str):
    """Remove a skill from this project."""
    project = _get_project()
    if project.drop(name):
        console.print(f"[green]Dropped {name}[/green]")
    else:
        console.print(f"[red]Skill '{name}' not in project[/red]")


@cli.command()
def sync():
    """Install missing skills from skills.json."""
    project = _get_project()
    synced = project.sync()
    if synced:
        console.print(f"[green]Synced: {', '.join(synced)}[/green]")
    else:
        console.print("[dim]Everything up to date.[/dim]")


@cli.command()
@click.argument("name", required=False)
def upgrade(name: str | None):
    """Update project skills to latest library versions."""
    project = _get_project()
    upgraded = project.upgrade(name=name)
    if upgraded:
        for skill_name, old, new in upgraded:
            console.print(f"[green]{skill_name}: {old} → {new}[/green]")
    else:
        console.print("[dim]Everything up to date.[/dim]")


@cli.command("inject")
@click.option("--format", "fmt", default="auto",
              type=click.Choice(["auto", "claude", "cursor", "openclaw", "codex"]))
@click.option("--file", "config_file", default=None, type=click.Path(),
              help="Custom config file path")
def inject_cmd(fmt: str, config_file: str | None):
    """Write skill references into agent config file."""
    project_dir = Path.cwd()
    file_path = Path(config_file) if config_file else None
    target = inject_skills(project_dir, fmt=fmt, config_file=file_path)
    console.print(f"[green]Injected skills into {target.name}[/green]")


@cli.command("enable")
@click.argument("name")
def enable_cmd(name: str):
    """Enable a skill in the project."""
    project = _get_project()
    if project.enable(name):
        console.print(f"[green]Enabled {name}[/green]")
    else:
        console.print(f"[red]Skill '{name}' not in project[/red]")


@cli.command("disable")
@click.argument("name")
def disable_cmd(name: str):
    """Disable a skill in the project (keep files, hide from agent)."""
    project = _get_project()
    if project.disable(name):
        console.print(f"[green]Disabled {name}[/green]")
    else:
        console.print(f"[red]Skill '{name}' not in project[/red]")


# ── Export/Import ──────────────────────────────────────────

@cli.command("export")
@click.argument("name")
@click.option("--version", default=None, help="Specific version (default: latest)")
@click.option("--output", default=None, type=click.Path(), help="Output directory")
def export_cmd(name: str, version: str | None, output: str | None):
    """Export a skill as a .skillpack archive."""
    lib = _get_library()
    skill = lib.info(name)
    if skill is None:
        console.print(f"[red]Skill '{name}' not found[/red]")
        return

    if version is None:
        ver = lib.db.get_latest_version(skill.id)
        if ver is None:
            console.print(f"[red]No versions for '{name}'[/red]")
            return
        version = ver.version

    skill_path = lib.get_skill_files_path(name, version)
    output_dir = Path(output) if output else Path.cwd()

    archive = export_skill(
        skill_path, name, version,
        {"description": skill.description, "author": skill.author, "tags": skill.tags},
        output_dir=output_dir,
    )
    console.print(f"[green]Exported {archive.name}[/green]")


@cli.command("import")
@click.argument("source")
@click.option("--name", default=None, help="Override skill name")
def import_cmd(source: str, name: str | None):
    """Import a skill from a .skillpack file or local directory."""
    lib = _get_library()
    source_path = Path(source)

    if source_path.suffix == ".skillpack":
        # Import from archive
        files_dir, metadata = import_skillpack(source_path)
        skill_name = name or metadata["name"]
        version = metadata.get("version", "v1")

        lib.publish(files_dir, name=skill_name, version=version)
        # Clean up temp dir
        shutil.rmtree(files_dir.parent)
        console.print(f"[green]Imported {skill_name}@{version} from {source_path.name}[/green]")

    elif source_path.is_dir():
        # Import from local directory
        skill_name, ver = lib.publish(source_path, name=name)
        console.print(f"[green]Imported {skill_name}@{ver}[/green]")

    else:
        console.print(f"[red]Source not found or unsupported: {source}[/red]")


if __name__ == "__main__":
    cli()
