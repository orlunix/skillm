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
from .core import Library, Project, get_active_library, create_library_from_remote
from .inject import inject as inject_skills
from .skillpack import export_skill, import_skillpack

console = Console()


def _get_library() -> Library:
    try:
        return get_active_library()
    except Exception:
        console.print("[red]Library not initialized. Run 'skillm library init' first.[/red]")
        sys.exit(1)


def _get_project(
    library: Library | None = None,
    agent: str = "claude",
    project_root: str | None = None,
) -> Project:
    project_dir = Path(project_root).resolve() if project_root else None
    return Project(
        project_dir=project_dir,
        library=library or _get_library(),
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


@library.command("snapshots")
def library_snapshots():
    """List database snapshots."""
    from .snapshot import list_snapshots
    lib = _get_library()
    snaps = list_snapshots(lib.config.library_path)

    if not snaps:
        console.print("[dim]No snapshots.[/dim]")
        return

    for i, (path, ts) in enumerate(snaps):
        size = _format_size(path.stat().st_size)
        marker = " [green]← latest[/green]" if i == 0 else ""
        console.print(f"  {path.name}  {ts}  ({size}){marker}")


@library.command("rollback")
@click.argument("snapshot", required=False)
def library_rollback(snapshot: str | None):
    """Rollback the database to a snapshot.

    Without arguments, rolls back to the most recent snapshot.
    Pass a snapshot filename to restore a specific one.
    """
    from .snapshot import list_snapshots, rollback, snapshot_dir

    lib = _get_library()
    snap_path = None
    if snapshot:
        snap_path = snapshot_dir(lib.config.library_path) / snapshot
        if not snap_path.exists():
            console.print(f"[red]Snapshot not found: {snapshot}[/red]")
            return

    try:
        restored = rollback(lib.config.library_path, snap_path)
        console.print(f"[green]Rolled back to {restored.name}[/green]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")


# ── Remote Management ─────────────────────────────────────

@cli.group()
def remote():
    """Manage remote libraries."""


@remote.command("add")
@click.argument("name")
@click.argument("path")
def remote_add(name: str, path: str):
    """Add a remote library.

    \b
    PATH can be:
      /path/to/library           Local path
      ssh://user@host:/path      SSH remote
    """
    from .remote import add_remote
    config = add_remote(name, path)
    console.print(f"[green]Added remote '{name}' → {path}[/green]")
    if config.active == name:
        console.print(f"[dim]Active remote: {name}[/dim]")


@remote.command("rm")
@click.argument("name")
def remote_rm(name: str):
    """Remove a remote library."""
    from .remote import remove_remote
    try:
        config = remove_remote(name)
        console.print(f"[green]Removed remote '{name}'[/green]")
        console.print(f"[dim]Active remote: {config.active}[/dim]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")


@remote.command("switch")
@click.argument("name")
def remote_switch(name: str):
    """Switch the active remote library."""
    from .remote import switch_remote
    try:
        switch_remote(name)
        console.print(f"[green]Switched to '{name}'[/green]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")


@remote.command("list")
def remote_list():
    """List all remote libraries."""
    from .remote import load_remotes
    config = load_remotes()

    if not config.remotes:
        console.print("[dim]No remotes configured.[/dim]")
        return

    for name, r in sorted(config.remotes.items()):
        marker = " [green]← active[/green]" if name == config.active else ""
        kind = "ssh" if r.is_ssh else "local"
        console.print(f"  [bold]{name}[/bold] ({kind}) {r.path}{marker}")


# ── Push / Pull ───────────────────────────────────────────

@cli.command("push")
@click.argument("remote_name")
def push_cmd(remote_name: str):
    """Push all skills to a remote library.

    Takes the latest version of each local skill and adds it to the
    remote. Version numbers are determined by the remote's history.
    """
    from .remote import load_remotes
    config = load_remotes()
    if remote_name not in config.remotes:
        console.print(f"[red]Remote '{remote_name}' not found[/red]")
        return
    if remote_name == config.active:
        console.print(f"[red]Cannot push to the active library ('{remote_name}'). Push to a different remote.[/red]")
        return

    local = _get_library()
    target = create_library_from_remote(config.remotes[remote_name])

    results = local.push(target)
    if not results:
        console.print("[dim]No skills to push.[/dim]")
        return

    new_count = 0
    updated_count = 0
    for name, local_ver, target_ver in results:
        # Check if skill existed on remote before
        console.print(f"  [green]{name}[/green] {local_ver} → {target_ver}")
        if target_ver == "v0.1":
            new_count += 1
        else:
            updated_count += 1

    parts = []
    if new_count:
        parts.append(f"{new_count} new")
    if updated_count:
        parts.append(f"{updated_count} updated")
    console.print(f"[green]Pushed {len(results)} skill(s) to {remote_name} ({', '.join(parts)})[/green]")


@cli.command("pull")
@click.argument("remote_name")
def pull_cmd(remote_name: str):
    """Pull all skills from a remote library.

    Takes the latest version of each remote skill and adds it to the
    local library. Version numbers are determined by local history.
    """
    from .remote import load_remotes
    config = load_remotes()
    if remote_name not in config.remotes:
        console.print(f"[red]Remote '{remote_name}' not found[/red]")
        return
    if remote_name == config.active:
        console.print(f"[red]Cannot pull from the active library ('{remote_name}'). Pull from a different remote.[/red]")
        return

    local = _get_library()
    source = create_library_from_remote(config.remotes[remote_name])

    results = local.pull(source)
    if not results:
        console.print("[dim]No skills to pull.[/dim]")
        return

    new_count = 0
    updated_count = 0
    for name, source_ver, local_ver in results:
        console.print(f"  [green]{name}[/green] {source_ver} → {local_ver}")
        if local_ver == "v0.1":
            new_count += 1
        else:
            updated_count += 1

    parts = []
    if new_count:
        parts.append(f"{new_count} new")
    if updated_count:
        parts.append(f"{updated_count} updated")
    console.print(f"[green]Pulled {len(results)} skill(s) from {remote_name} ({', '.join(parts)})[/green]")


# ── Skill Operations ───────────────────────────────────────

@cli.command("add")
@click.argument("source", type=click.Path(exists=True))
@click.option("--name", default=None, help="Override skill name")
@click.option("--major", is_flag=True, help="Bump major version (v1.0 → v2.0)")
@click.option("--version", default=None, help="Explicit version string")
@click.option("-c", "--category", default=None, help="Set skill category")
def add_cmd(source: str, name: str | None, major: bool, version: str | None, category: str | None):
    """Add a skill to the library. Creates a new minor version by default."""
    from .metadata import extract_metadata
    from .scan import scan_skill_content, diff_requires

    lib = _get_library()
    source_path = Path(source)

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
    except (FileNotFoundError, Exception):
        pass

    skill_name, ver = lib.publish(source_path, name=name, version=version, major=major)

    if category:
        skill = lib.info(skill_name)
        if skill:
            skill.category = category.strip().lower()
            lib.db.update_skill(skill)

    console.print(f"[green]Added {skill_name}@{ver}[/green]")


@cli.command("update")
@click.argument("source", type=click.Path(exists=True))
@click.option("--name", default=None, help="Override skill name")
def update_cmd(source: str, name: str | None):
    """Replace the latest version of an existing skill in-place.

    Unlike 'add' which creates a new version, 'update' overwrites the
    latest version. Useful for fixing typos or small corrections.

    Errors if the skill doesn't exist — use 'add' for new skills.
    """
    lib = _get_library()
    source_path = Path(source)
    try:
        skill_name, ver = lib.override(source_path, name=name)
        console.print(f"[green]Updated {skill_name}@{ver}[/green]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")


@cli.command("rm")
@click.argument("name")
@click.option("--version", default=None, help="Remove specific version only")
def rm_cmd(name: str, version: str | None):
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
    if skill.category:
        console.print(f"[bold]Category:[/bold] {skill.category}")
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
@click.option("-c", "--category", default=None, help="Filter by category")
def list_cmd(category: str | None):
    """List all skills in the library."""
    lib = _get_library()

    if category:
        skills = lib.db.list_skills_by_category(category)
    else:
        skills = lib.list_skills()

    if not skills:
        msg = f"No skills in category '{category}'." if category else "No skills in library."
        console.print(f"[dim]{msg}[/dim]")
        return

    if not category:
        # Group by category
        grouped: dict[str, list] = {}
        for skill in skills:
            cat = skill.category or "general"
            grouped.setdefault(cat, []).append(skill)

        for cat in sorted(grouped):
            table = Table(show_header=True, title=cat, title_style="bold cyan")
            table.add_column("Name", style="bold")
            table.add_column("Latest")
            table.add_column("Tags")
            table.add_column("Size", justify="right")

            for skill in grouped[cat]:
                latest = skill.versions[-1] if skill.versions else None
                table.add_row(
                    skill.name,
                    latest.version if latest else "-",
                    ", ".join(skill.tags) if skill.tags else "",
                    _format_size(latest.total_size) if latest else "-",
                )

            console.print(table)
            console.print()
    else:
        table = Table(show_header=True, title=category, title_style="bold cyan")
        table.add_column("Name", style="bold")
        table.add_column("Latest")
        table.add_column("Tags")
        table.add_column("Size", justify="right")

        for skill in skills:
            latest = skill.versions[-1] if skill.versions else None
            table.add_row(
                skill.name,
                latest.version if latest else "-",
                ", ".join(skill.tags) if skill.tags else "",
                _format_size(latest.total_size) if latest else "-",
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


@cli.command("categories")
def categories_cmd():
    """Show all categories with skill counts."""
    lib = _get_library()
    cats = lib.db.list_categories()

    if not cats:
        console.print("[dim]No skills in library.[/dim]")
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
    lib = _get_library()
    skill = lib.info(name)
    if skill is None:
        console.print(f"[red]Skill '{name}' not found[/red]")
        return

    skill.category = category.strip().lower()
    from datetime import datetime, timezone
    skill.updated_at = datetime.now(timezone.utc).isoformat()
    lib.db.update_skill(skill)
    console.print(f"[green]{name} → {skill.category}[/green]")


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

# Common options for project commands
_agent_option = click.option("--agent", "-a", default="claude",
    type=click.Choice(["claude", "cursor", "codex", "openclaw"]),
    help="Target agent (default: claude)")
_root_option = click.option("--project-root", "-r", default=None,
    type=click.Path(exists=True), help="Project root directory (default: cwd)")


@cli.command("install")
@click.argument("name")
@click.option("--pin", is_flag=True, help="Pin to this version")
@_agent_option
@_root_option
def install_cmd(name: str, pin: bool, agent: str, project_root: str | None):
    """Install a skill from the library into this project."""
    version = None
    if "@" in name:
        name, version = name.rsplit("@", 1)

    project = _get_project(agent=agent, project_root=project_root)
    ver = project.add(name, version=version, pin=pin)
    console.print(f"[green]Installed {name}@{ver} → {project.skills_dir.relative_to(project.project_dir)}/[/green]")

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
                    console.print(f"  [red]✗[/red] {r.name} — {r.message}")


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
    """Update project skills to latest library versions."""
    project = _get_project(agent=agent, project_root=project_root)
    upgraded = project.upgrade(name=name)
    if upgraded:
        for skill_name, old, new in upgraded:
            console.print(f"[green]{skill_name}: {old} → {new}[/green]")
    else:
        console.print("[dim]Everything up to date.[/dim]")


# ── Environment Check ──────────────────────────────────────

def _print_check_report(report):
    """Print a skill check report."""
    from .check import SkillCheckReport
    if not report.has_checks:
        console.print(f"  [dim]No requirements declared[/dim]")
        return

    for r in report.results:
        icon = "[green]✓[/green]" if r.ok else "[red]✗[/red]"
        console.print(f"  {icon} [bold]{r.name}[/bold] — {r.message}")

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

    lib = _get_library()
    skill = lib.info(name)
    if skill is None:
        console.print(f"[red]Skill '{name}' not found[/red]")
        return

    # Get latest version files to read SKILL.md
    latest = lib.db.get_latest_version(skill.id)
    if latest is None:
        console.print(f"[red]No versions for '{name}'[/red]")
        return

    skill_dir = lib.get_skill_files_path(name, latest.version)
    meta = extract_metadata(skill_dir)

    # Check declared requirements
    requires = meta.requires
    console.print(f"[bold]{name}[/bold] environment check:")

    if scan:
        # Auto-scan content and merge with declared
        detected = scan_skill_content(meta.content)
        missing = diff_requires(requires, detected)

        if missing.has_findings:
            # Merge detected into requires for checking
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
    for skill_name, info in manifest.items():
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

        if scan:
            detected = scan_skill_content(meta.content)
            missing_fm = diff_requires(meta.requires, detected)
            if missing_fm.has_findings:
                console.print("  [dim]Auto-detected (not in frontmatter):[/dim]")
                if missing_fm.bins:
                    console.print(f"    bins: {missing_fm.bins}")
                if missing_fm.packages:
                    console.print(f"    packages: {missing_fm.packages}")
                if missing_fm.env:
                    console.print(f"    env: {missing_fm.env}")

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
@click.option("--ref", default=None, help="Git ref for GitHub imports (tag, branch)")
@click.option("--token", default=None, help="Auth token (GitHub or ClawHub)")
def import_cmd(source: str, name: str | None, ref: str | None, token: str | None):
    """Import a skill from various sources.

    \b
    Sources:
      ./path/to/dir          Local directory
      ./skill.skillpack      Skillpack archive
      owner/repo             GitHub repository
      owner/repo/subpath     GitHub subdirectory
      clawhub:slug           ClawHub registry
      clawhub:slug@1.0.0     ClawHub specific version
      https://url/skill.zip  URL (tar.gz or zip)
    """
    from .importers import (
        detect_source_type,
        import_from_clawhub,
        import_from_github,
        import_from_url,
    )

    lib = _get_library()

    try:
        source_type = detect_source_type(source)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        return

    try:
        if source_type == "skillpack":
            files_dir, metadata = import_skillpack(Path(source))
            skill_name = name or metadata["name"]
            version = metadata.get("version", "v1")
            lib.publish(files_dir, name=skill_name, version=version, source=source)
            shutil.rmtree(files_dir.parent)
            console.print(f"[green]Imported {skill_name}@{version} from {Path(source).name}[/green]")

        elif source_type == "directory":
            skill_name, ver = lib.publish(Path(source), name=name)
            console.print(f"[green]Imported {skill_name}@{ver}[/green]")

        elif source_type == "github":
            console.print(f"[dim]Fetching from GitHub: {source}...[/dim]")
            skill_dir, source_str = import_from_github(source, ref=ref, token=token)
            skill_name, ver = lib.publish(skill_dir, name=name, source=source_str)
            shutil.rmtree(skill_dir.parent if skill_dir.parent.name.startswith("skillm-gh-") else skill_dir)
            console.print(f"[green]Imported {skill_name}@{ver} from GitHub ({source_str})[/green]")

        elif source_type == "clawhub":
            console.print(f"[dim]Fetching from ClawHub: {source}...[/dim]")
            skill_dir, source_str = import_from_clawhub(source, token=token)
            skill_name, ver = lib.publish(skill_dir, name=name, source=source_str)
            shutil.rmtree(skill_dir.parent if skill_dir.parent.name.startswith("skillm-ch-") else skill_dir)
            console.print(f"[green]Imported {skill_name}@{ver} from ClawHub ({source_str})[/green]")

        elif source_type == "url":
            console.print(f"[dim]Downloading: {source}...[/dim]")
            skill_dir, source_str = import_from_url(source)
            skill_name, ver = lib.publish(skill_dir, name=name, source=source_str)
            shutil.rmtree(skill_dir.parent if skill_dir.parent.name.startswith("skillm-url-") else skill_dir)
            console.print(f"[green]Imported {skill_name}@{ver} from URL[/green]")

    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
    except httpx.HTTPStatusError as e:
        console.print(f"[red]HTTP error: {e.response.status_code} — {e.request.url}[/red]")
    except Exception as e:
        console.print(f"[red]Import failed: {e}[/red]")


if __name__ == "__main__":
    cli()
