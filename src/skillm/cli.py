"""Click CLI for skillm v2 — git-backed package manager."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import Config, Source, load_config, save_config
from .core import SourceManager, Project
from .git import GitError
from .inject import inject as inject_skills
from .skillpack import export_skill, import_skillpack

console = Console()


def _get_source_manager() -> SourceManager:
    try:
        return SourceManager()
    except Exception:
        config = Config()
        return SourceManager(config)


def _get_project(
    source_manager: SourceManager | None = None,
    agent: str = "claude",
    project_root: str | None = None,
) -> Project:
    project_dir = Path(project_root).resolve() if project_root else None
    return Project(
        project_dir=project_dir,
        source_manager=source_manager or _get_source_manager(),
        agent=agent,
    )


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
    """skillm — Git-backed skill manager for AI coding agents."""


# ── Source Management ──────────────────────────────────────

@cli.group()
def source():
    """Manage skill sources (git repositories)."""


@source.command("init")
@click.argument("name")
@click.argument("path")
@click.option("--priority", "-p", default=10, help="Source priority (lower = higher)")
def source_init(name: str, path: str, priority: int):
    """Initialize a new source (creates git repo if needed)."""
    sm = _get_source_manager()
    src = sm.init_source(name, path, priority)
    console.print(f"[green]Initialized source '{name}' at {src.resolved_path}[/green]")


@source.command("add")
@click.argument("name")
@click.argument("url")
@click.option("--priority", "-p", default=10, help="Source priority (lower = higher)")
def source_add(name: str, url: str, priority: int):
    """Add an existing source."""
    sm = _get_source_manager()
    sm.add_source(name, url, priority)
    console.print(f"[green]Added source '{name}' → {url}[/green]")


@source.command("rm")
@click.argument("name")
def source_rm(name: str):
    """Remove a source (does not delete the git repo)."""
    sm = _get_source_manager()
    sm.remove_source(name)
    console.print(f"[green]Removed source '{name}'[/green]")


@source.command("list")
def source_list():
    """List all configured sources."""
    sm = _get_source_manager()
    if not sm.config.sources:
        console.print("[dim]No sources configured.[/dim]")
        return

    default = sm.config.settings.default_source
    for src in sm.config.sources:
        marker = " [green]<- default[/green]" if src.name == default else ""
        remote_info = " (remote)" if src.is_remote else ""
        console.print(
            f"  [bold]{src.name}[/bold] (priority: {src.priority}){remote_info} "
            f"{src.url}{marker}"
        )


@source.command("default")
@click.argument("name")
def source_default(name: str):
    """Set the default source."""
    sm = _get_source_manager()
    sm.set_default(name)
    console.print(f"[green]Default source: {name}[/green]")


# ── Skill Operations ──────────────────────────────────────

@cli.command("add")
@click.argument("source_dir", type=click.Path(exists=True))
@click.option("--name", default=None, help="Override skill name")
@click.option("--source", "-s", "source_name", default=None, help="Target source")
@click.option("--message", "-m", default=None, help="Commit message")
@click.option("-c", "--category", default=None, help="Set skill category")
def add_cmd(source_dir: str, name: str | None, source_name: str | None, message: str | None, category: str | None):
    """Add a skill to a source repository (git commit)."""
    from .metadata import extract_metadata
    from .scan import scan_skill_content, diff_requires

    sm = _get_source_manager()
    source_path = Path(source_dir)

    # Auto-scan to suggest missing requirements
    try:
        meta = extract_metadata(source_path)
        detected = scan_skill_content(meta.content)
        missing = diff_requires(meta.requires, detected)
        if missing.has_findings:
            console.print("[yellow]Detected requirements not in frontmatter:[/yellow]")
            if missing.bins:
                console.print(f"  bins: {missing.bins}")
            if missing.packages:
                console.print(f"  packages: {missing.packages}")
            if missing.env:
                console.print(f"  env: {missing.env}")
            console.print("[dim]Consider adding these to your SKILL.md frontmatter.[/dim]")
    except Exception:
        pass

    skill_name, src_name = sm.add_skill(source_path, source_name=source_name, name=name, message=message)

    if category:
        skill = sm.info(skill_name, source=src_name)
        if skill:
            skill.category = category.strip().lower()
            from datetime import datetime, timezone
            skill.updated_at = datetime.now(timezone.utc).isoformat()
            sm.db.update_skill(skill)

    console.print(f"[green]Added {skill_name} to source '{src_name}'[/green]")


@cli.command("publish")
@click.argument("name")
@click.option("--major", is_flag=True, help="Bump major version (v1.0 -> v2.0)")
@click.option("--source", "-s", "source_name", default=None, help="Target source")
@click.option("--message", "-m", default=None, help="Tag message")
def publish_cmd(name: str, major: bool, source_name: str | None, message: str | None):
    """Create a version tag for a skill."""
    sm = _get_source_manager()
    skill_name, version = sm.publish(name, source_name=source_name, major=major, message=message)
    console.print(f"[green]Published {skill_name}@{version}[/green]")


@cli.command("rm")
@click.argument("name")
@click.option("--version", default=None, help="Remove specific version only")
@click.option("--source", "-s", "source_name", default=None, help="Target source")
def rm_cmd(name: str, version: str | None, source_name: str | None):
    """Remove a skill from a source."""
    sm = _get_source_manager()
    sm.remove_skill(name, source_name=source_name, version=version)
    target = f"{name}@{version}" if version else name
    console.print(f"[green]Removed {target}[/green]")


@cli.command()
@click.argument("name")
@click.option("--source", "-s", "source_name", default=None, help="Source to query")
def info(name: str, source_name: str | None):
    """Show skill details."""
    sm = _get_source_manager()
    skill = sm.info(name, source=source_name)
    if skill is None:
        console.print(f"[red]Skill '{name}' not found[/red]")
        return

    console.print(f"[bold]Name:[/bold] {skill.name}")
    console.print(f"[bold]Source:[/bold] {skill.source}")
    console.print(f"[bold]Description:[/bold] {skill.description}")
    if skill.category:
        console.print(f"[bold]Category:[/bold] {skill.category}")
    if skill.tags:
        console.print(f"[bold]Tags:[/bold] {', '.join(skill.tags)}")
    if skill.author:
        console.print(f"[bold]Author:[/bold] {skill.author}")
    if skill.versions:
        ver_str = ", ".join(v.version for v in skill.versions)
        latest = skill.versions[-1].version
        console.print(f"[bold]Versions:[/bold] {ver_str} (latest: {latest})")


@cli.command("list")
@click.option("-c", "--category", default=None, help="Filter by category")
@click.option("--source", "-s", "source_name", default=None, help="Filter by source")
def list_cmd(category: str | None, source_name: str | None):
    """List all skills."""
    sm = _get_source_manager()

    if category:
        skills = sm.db.list_skills_by_category(category)
    else:
        skills = sm.list_skills(source=source_name)

    if not skills:
        msg = f"No skills in category '{category}'." if category else "No skills found."
        console.print(f"[dim]{msg}[/dim]")
        return

    # Group by source
    grouped: dict[str, list] = {}
    for skill in skills:
        grouped.setdefault(skill.source, []).append(skill)

    for src_name in sorted(grouped):
        table = Table(show_header=True, title=src_name, title_style="bold cyan")
        table.add_column("Name", style="bold")
        table.add_column("Latest")
        table.add_column("Category")
        table.add_column("Tags")

        for skill in grouped[src_name]:
            latest = skill.versions[-1] if skill.versions else None
            table.add_row(
                skill.name,
                latest.version if latest else "(unpublished)",
                skill.category or "",
                ", ".join(skill.tags) if skill.tags else "",
            )

        console.print(table)
        console.print()


@cli.command()
@click.argument("name")
@click.option("--source", "-s", "source_name", default=None, help="Source to query")
def versions(name: str, source_name: str | None):
    """List all versions of a skill."""
    sm = _get_source_manager()
    skill = sm.info(name, source=source_name)
    if skill is None:
        console.print(f"[red]Skill '{name}' not found[/red]")
        return

    if not skill.versions:
        console.print("[dim]No published versions. Run: skillm publish {name}[/dim]")
        return

    table = Table(show_header=True)
    table.add_column("Version")
    table.add_column("Published")

    for v in skill.versions:
        latest_marker = " (latest)" if v == skill.versions[-1] else ""
        table.add_row(
            v.version + latest_marker,
            v.published_at[:10] if v.published_at else "-",
        )

    console.print(table)


@cli.command()
@click.argument("query")
def search(query: str):
    """Search skills across all sources."""
    sm = _get_source_manager()
    results = sm.search(query)

    if not results:
        console.print("[dim]No results.[/dim]")
        return

    for skill in results:
        latest = skill.versions[-1] if skill.versions else None
        ver = f"@{latest.version}" if latest else ""
        tags = f" [{', '.join(skill.tags)}]" if skill.tags else ""
        console.print(f"[bold]{skill.name}[/bold]{ver} ({skill.source}){tags}")
        if skill.description:
            console.print(f"  {skill.description}")


@cli.command("categories")
def categories_cmd():
    """Show all categories with skill counts."""
    sm = _get_source_manager()
    cats = sm.db.list_categories()
    if not cats:
        console.print("[dim]No skills found.[/dim]")
        return

    table = Table(show_header=True)
    table.add_column("Category", style="bold")
    table.add_column("Skills", justify="right")
    for cat, count in cats:
        table.add_row(cat, str(count))
    console.print(table)


@cli.command("categorize")
@click.argument("name")
@click.argument("category")
def categorize_cmd(name: str, category: str):
    """Set the category of a skill."""
    sm = _get_source_manager()
    skill = sm.info(name)
    if skill is None:
        console.print(f"[red]Skill '{name}' not found[/red]")
        return

    skill.category = category.strip().lower()
    from datetime import datetime, timezone
    skill.updated_at = datetime.now(timezone.utc).isoformat()
    sm.db.update_skill(skill)
    console.print(f"[green]{name} -> {skill.category}[/green]")


@cli.command()
@click.argument("name")
@click.argument("tags", nargs=-1, required=True)
def tag(name: str, tags: tuple[str]):
    """Add tags to a skill."""
    sm = _get_source_manager()
    if sm.tag(name, list(tags)):
        console.print(f"[green]Tagged {name} with: {', '.join(tags)}[/green]")
    else:
        console.print(f"[red]Skill '{name}' not found[/red]")


@cli.command()
@click.argument("name")
@click.argument("tags", nargs=-1, required=True)
def untag(name: str, tags: tuple[str]):
    """Remove tags from a skill."""
    sm = _get_source_manager()
    if sm.untag(name, list(tags)):
        console.print(f"[green]Untagged {name}: {', '.join(tags)}[/green]")
    else:
        console.print(f"[red]Skill '{name}' not found[/red]")


# ── Push / Pull / Log / Diff ─────────────────────────────

@cli.command("push")
@click.argument("source_name", required=False, default=None)
def push_cmd(source_name: str | None):
    """Push a source repo to its remote (git push --tags)."""
    sm = _get_source_manager()
    try:
        result = sm.push(source_name)
        src = sm.resolve_source(source_name)
        console.print(f"[green]Pushed '{src.name}'[/green]")
        if result:
            console.print(f"[dim]{result}[/dim]")
    except GitError as e:
        console.print(f"[red]{e}[/red]")


@cli.command("pull")
@click.argument("source_name", required=False, default=None)
def pull_cmd(source_name: str | None):
    """Pull a source repo from its remote (git pull + cache rebuild)."""
    sm = _get_source_manager()
    try:
        result = sm.pull(source_name)
        src = sm.resolve_source(source_name)
        console.print(f"[green]Pulled '{src.name}'[/green]")
        if result:
            console.print(f"[dim]{result}[/dim]")
    except GitError as e:
        console.print(f"[red]{e}[/red]")


@cli.command("log")
@click.argument("name")
@click.option("--source", "-s", "source_name", default=None, help="Source to query")
@click.option("-n", "--max-count", default=20, help="Max number of log entries")
def log_cmd(name: str, source_name: str | None, max_count: int):
    """Show git log for a skill."""
    sm = _get_source_manager()
    try:
        output = sm.log(name, source_name=source_name, max_count=max_count)
        if output:
            console.print(output)
        else:
            console.print("[dim]No history.[/dim]")
    except GitError as e:
        console.print(f"[red]{e}[/red]")


@cli.command("diff")
@click.argument("name")
@click.option("--source", "-s", "source_name", default=None, help="Source to query")
def diff_cmd(name: str, source_name: str | None):
    """Show uncommitted changes for a skill."""
    sm = _get_source_manager()
    try:
        output = sm.diff(name, source_name=source_name)
        if output:
            console.print(output)
        else:
            console.print("[dim]No uncommitted changes.[/dim]")
    except GitError as e:
        console.print(f"[red]{e}[/red]")


# ── Cache Management ──────────────────────────────────────

@cli.group()
def cache():
    """Manage the skill cache index."""


@cache.command("rebuild")
@click.option("--source", "-s", "source_name", default=None, help="Rebuild specific source only")
def cache_rebuild(source_name: str | None):
    """Rebuild the cache index from git repositories."""
    sm = _get_source_manager()
    count = sm.rebuild_cache(source_name=source_name)
    console.print(f"[green]Rebuilt cache: {count} skill(s) indexed.[/green]")


@cache.command("stats")
def cache_stats():
    """Show cache statistics."""
    sm = _get_source_manager()
    s = sm.stats()
    console.print(
        f"Skills: [bold]{s['skills']}[/bold] | "
        f"Versions: [bold]{s['versions']}[/bold] | "
        f"Sources: [bold]{s['sources']}[/bold]"
    )


# ── Project Operations ────────────────────────────────────

_agent_option = click.option("--agent", "-a", default="claude",
    type=click.Choice(["claude", "cursor", "codex", "openclaw"]),
    help="Target agent (default: claude)")
_root_option = click.option("--project-root", "-r", default=None,
    type=click.Path(exists=True), help="Project root directory (default: cwd)")


@cli.command("install")
@click.argument("name")
@click.option("--pin", is_flag=True, help="Pin to this version")
@click.option("--source", "-s", "source_name", default=None, help="Install from specific source")
@_agent_option
@_root_option
def install_cmd(name: str, pin: bool, source_name: str | None, agent: str, project_root: str | None):
    """Install a skill from a source into this project."""
    version = None
    if "@" in name:
        name, version = name.rsplit("@", 1)

    project = _get_project(agent=agent, project_root=project_root)
    try:
        ver = project.add(name, version=version, pin=pin, source=source_name)
        console.print(
            f"[green]Installed {name}@{ver} -> "
            f"{project.skills_dir.relative_to(project.project_dir)}/[/green]"
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        return

    # Run env check and warn
    from .check import check_requirements
    from .metadata import extract_metadata
    skill_dir = project.skills_dir / name
    if skill_dir.exists():
        meta = extract_metadata(skill_dir)
        report = check_requirements(name, meta.requires)
        if report.has_checks and not report.all_ok:
            console.print(f"[yellow]Warning: {report.failed} unmet requirement(s):[/yellow]")
            for r in report.results:
                if not r.ok:
                    console.print(f"  [red]x[/red] {r.name} -- {r.message}")


@cli.command("uninstall")
@click.argument("name")
@_agent_option
@_root_option
def uninstall_cmd(name: str, agent: str, project_root: str | None):
    """Uninstall a skill from this project."""
    project = _get_project(agent=agent, project_root=project_root)
    if project.drop(name):
        console.print(f"[green]Uninstalled {name}[/green]")
    else:
        console.print(f"[red]Skill '{name}' not in project[/red]")


@cli.command()
@_agent_option
@_root_option
def sync(agent: str, project_root: str | None):
    """Install missing skills from skills.json."""
    project = _get_project(agent=agent, project_root=project_root)
    synced = project.sync()
    if synced:
        console.print(f"[green]Synced: {', '.join(synced)}[/green]")
    else:
        console.print("[dim]Everything up to date.[/dim]")


@cli.command()
@click.argument("name", required=False)
@_agent_option
@_root_option
def upgrade(name: str | None, agent: str, project_root: str | None):
    """Update project skills to latest versions."""
    project = _get_project(agent=agent, project_root=project_root)
    upgraded = project.upgrade(name=name)
    if upgraded:
        for skill_name, old, new in upgraded:
            console.print(f"[green]{skill_name}: {old} -> {new}[/green]")
    else:
        console.print("[dim]Everything up to date.[/dim]")


# ── Environment Check ─────────────────────────────────────

def _print_check_report(report):
    if not report.has_checks:
        console.print(f"  [dim]No requirements declared[/dim]")
        return
    for r in report.results:
        icon = "[green]v[/green]" if r.ok else "[red]x[/red]"
        console.print(f"  {icon} [bold]{r.name}[/bold] -- {r.message}")
    if report.all_ok:
        console.print(f"  [green]All {report.passed} checks passed[/green]")
    else:
        console.print(f"  [yellow]{report.passed} passed, {report.failed} failed[/yellow]")


@cli.command("check")
@click.argument("name")
@click.option("--scan/--no-scan", default=True, help="Auto-scan content for undeclared requirements")
def check_cmd(name: str, scan: bool):
    """Check if a skill's requirements are met on this machine."""
    from .check import check_requirements
    from .metadata import extract_metadata
    from .scan import scan_skill_content, diff_requires

    sm = _get_source_manager()
    skill = sm.info(name)
    if skill is None:
        console.print(f"[red]Skill '{name}' not found[/red]")
        return

    skill_dir = sm.get_skill_files(name)
    meta = extract_metadata(skill_dir)
    requires = meta.requires

    console.print(f"[bold]{name}[/bold] environment check:")

    if scan:
        detected = scan_skill_content(meta.content)
        missing = diff_requires(requires, detected)
        if missing.has_findings:
            if not isinstance(requires, dict):
                requires = {"bins": requires} if requires else {}
            merged = dict(requires)
            if missing.bins:
                merged["bins"] = list(set(merged.get("bins", []) + missing.bins))
            if missing.packages:
                merged["packages"] = list(set(merged.get("bins", []) + missing.packages))
            if missing.env:
                merged["env"] = list(set(merged.get("env", []) + missing.env))
            requires = merged

    report = check_requirements(name, requires)
    _print_check_report(report)

    if scan:
        detected = scan_skill_content(meta.content)
        missing = diff_requires(meta.requires, detected)
        if missing.has_findings:
            console.print()
            console.print("  [dim]Auto-detected (not in frontmatter):[/dim]")
            if missing.bins:
                console.print(f"    bins: {missing.bins}")
            if missing.packages:
                console.print(f"    packages: {missing.packages}")
            if missing.env:
                console.print(f"    env: {missing.env}")


@cli.command("doctor")
@click.option("--scan/--no-scan", default=True, help="Auto-scan content for undeclared requirements")
@_agent_option
@_root_option
def doctor_cmd(scan: bool, agent: str, project_root: str | None):
    """Check requirements for all installed project skills."""
    from .check import check_requirements
    from .metadata import extract_metadata
    from .scan import scan_skill_content, diff_requires

    project = _get_project(agent=agent, project_root=project_root)
    manifest = project.list_skills()

    if not manifest:
        console.print("[dim]No skills in project.[/dim]")
        return

    all_ok = True
    for skill_name, skill_info in manifest.items():
        skill_dir = project.skills_dir / skill_name
        if not skill_dir.exists():
            console.print(f"[bold]{skill_name}[/bold]: [red]not installed (run skillm sync)[/red]")
            all_ok = False
            continue

        meta = extract_metadata(skill_dir)
        requires = meta.requires

        if scan:
            detected = scan_skill_content(meta.content)
            missing = diff_requires(requires, detected)
            if missing.has_findings:
                if not isinstance(requires, dict):
                    requires = {"bins": requires} if requires else {}
                merged = dict(requires)
                if missing.bins:
                    merged["bins"] = list(set(merged.get("bins", []) + missing.bins))
                if missing.packages:
                    merged["packages"] = list(set(merged.get("packages", []) + missing.packages))
                if missing.env:
                    merged["env"] = list(set(merged.get("env", []) + missing.env))
                requires = merged

        console.print(f"[bold]{skill_name}[/bold]:")
        report = check_requirements(skill_name, requires)
        _print_check_report(report)

        if not report.all_ok:
            all_ok = False
        console.print()

    if all_ok:
        console.print("[green]All skills OK.[/green]")
    else:
        console.print("[yellow]Some skills have unmet requirements.[/yellow]")


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
@_agent_option
@_root_option
def enable_cmd(name: str, agent: str, project_root: str | None):
    """Enable a skill in the project."""
    project = _get_project(agent=agent, project_root=project_root)
    if project.enable(name):
        console.print(f"[green]Enabled {name}[/green]")
    else:
        console.print(f"[red]Skill '{name}' not in project[/red]")


@cli.command("disable")
@click.argument("name")
@_agent_option
@_root_option
def disable_cmd(name: str, agent: str, project_root: str | None):
    """Disable a skill in the project (keep files, hide from agent)."""
    project = _get_project(agent=agent, project_root=project_root)
    if project.disable(name):
        console.print(f"[green]Disabled {name}[/green]")
    else:
        console.print(f"[red]Skill '{name}' not in project[/red]")


# ── Export/Import ─────────────────────────────────────────

@cli.command("export")
@click.argument("name")
@click.option("--version", default=None, help="Specific version (default: latest)")
@click.option("--output", default=None, type=click.Path(), help="Output directory")
def export_cmd(name: str, version: str | None, output: str | None):
    """Export a skill as a .skillpack archive."""
    sm = _get_source_manager()
    skill = sm.info(name)
    if skill is None:
        console.print(f"[red]Skill '{name}' not found[/red]")
        return

    if version is None:
        latest = sm.db.get_latest_version(skill.id)
        version = latest.version if latest else None

    skill_path = sm.get_skill_files(name, version=version)
    output_dir = Path(output) if output else Path.cwd()

    archive = export_skill(
        skill_path, name, version or "HEAD",
        {"description": skill.description, "author": skill.author, "tags": skill.tags},
        output_dir=output_dir,
    )
    console.print(f"[green]Exported {archive.name}[/green]")


@cli.command("import")
@click.argument("import_source")
@click.option("--name", default=None, help="Override skill name")
@click.option("--source", "-s", "source_name", default=None, help="Target source")
@click.option("--ref", default=None, help="Git ref for GitHub imports (tag, branch)")
@click.option("--token", default=None, help="Auth token (GitHub or ClawHub)")
def import_cmd(import_source: str, name: str | None, source_name: str | None, ref: str | None, token: str | None):
    """Import a skill from various sources.

    \b
    Sources:
      ./path/to/dir          Local directory
      ./skill.skillpack      Skillpack archive
      owner/repo             GitHub repository
      clawhub:slug           ClawHub registry
      https://url/skill.zip  URL (tar.gz or zip)
    """
    import httpx
    from .importers import (
        detect_source_type,
        import_from_clawhub,
        import_from_github,
        import_from_url,
    )

    sm = _get_source_manager()

    try:
        source_type = detect_source_type(import_source)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        return

    try:
        if source_type == "skillpack":
            files_dir, metadata = import_skillpack(Path(import_source))
            skill_name = name or metadata["name"]
            sm.add_skill(files_dir, source_name=source_name, name=skill_name)
            shutil.rmtree(files_dir.parent)
            console.print(f"[green]Imported {skill_name} from {Path(import_source).name}[/green]")

        elif source_type == "directory":
            skill_name, src_name = sm.add_skill(Path(import_source), source_name=source_name, name=name)
            console.print(f"[green]Imported {skill_name} to source '{src_name}'[/green]")

        elif source_type == "github":
            console.print(f"[dim]Fetching from GitHub: {import_source}...[/dim]")
            skill_dir, source_str = import_from_github(import_source, ref=ref, token=token)
            skill_name, src_name = sm.add_skill(skill_dir, source_name=source_name, name=name)
            shutil.rmtree(skill_dir.parent if skill_dir.parent.name.startswith("skillm-gh-") else skill_dir)
            console.print(f"[green]Imported {skill_name} from GitHub ({source_str})[/green]")

        elif source_type == "clawhub":
            console.print(f"[dim]Fetching from ClawHub: {import_source}...[/dim]")
            skill_dir, source_str = import_from_clawhub(import_source, token=token)
            skill_name, src_name = sm.add_skill(skill_dir, source_name=source_name, name=name)
            shutil.rmtree(skill_dir.parent if skill_dir.parent.name.startswith("skillm-ch-") else skill_dir)
            console.print(f"[green]Imported {skill_name} from ClawHub ({source_str})[/green]")

        elif source_type == "url":
            console.print(f"[dim]Downloading: {import_source}...[/dim]")
            skill_dir, source_str = import_from_url(import_source)
            skill_name, src_name = sm.add_skill(skill_dir, source_name=source_name, name=name)
            shutil.rmtree(skill_dir.parent if skill_dir.parent.name.startswith("skillm-url-") else skill_dir)
            console.print(f"[green]Imported {skill_name} from URL[/green]")

    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
    except httpx.HTTPStatusError as e:
        console.print(f"[red]HTTP error: {e.response.status_code} -- {e.request.url}[/red]")
    except Exception as e:
        console.print(f"[red]Import failed: {e}[/red]")


# ── Migration ─────────────────────────────────────────────

@cli.command("migrate")
def migrate_cmd():
    """Migrate from skillm v1 config to v2 (sources.toml)."""
    from .config import migrate_config
    result = migrate_config()
    if result:
        console.print("[green]Migrated to sources.toml format.[/green]")
        for src in result.sources:
            console.print(f"  Source: {src.name} -> {src.url}")
    else:
        console.print("[dim]Nothing to migrate (already on v2 or no v1 config found).[/dim]")


if __name__ == "__main__":
    cli()
