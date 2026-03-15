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
from .core import Library, Project, get_library
from .inject import inject as inject_skills
from .skillpack import export_skill, import_skillpack

console = Console()


def _get_library() -> Library:
    try:
        return get_library()
    except Exception:
        # Auto-init local library on first use
        config = Config()
        lib = Library(config)
        lib.init()
        return lib


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


# ── Branch management ──────────────────────────────────────

@cli.command("branch")
@click.argument("name", required=False, default=None)
@click.option("-n", "--new", "create_new", is_flag=True, help="Create a new branch (forks from current)")
@click.option("--empty", is_flag=True, help="With -n: start empty instead of forking")
@click.option("--reset", is_flag=True, help="Reset branch to remote/initial state (drops local commits)")
@click.option("--rm", "remove", is_flag=True, help="Delete a branch")
@click.option("--yes", is_flag=True, help="Skip confirmation for --rm/--reset")
def branch_cmd(name: str | None, create_new: bool, empty: bool, reset: bool, remove: bool, yes: bool):
    """Switch, create, delete, or list branches.

    \b
    skillm branch                    List all branches
    skillm branch infra              Switch to branch (auto-commits changes)
    skillm branch infra --reset      Reset branch to remote/initial state
    skillm branch -n infra           Fork current branch as 'infra'
    skillm branch -n infra --empty   Create empty branch
    skillm branch --rm infra         Delete branch
    """
    lib = _get_library()

    # No name → list branches
    if name is None:
        current = lib.current_library()
        branches = lib.list_libraries()

        if not branches:
            console.print("[dim]No branches.[/dim]")
            return

        for branch in branches:
            marker = "* " if branch == current else "  "
            display = f"[bold]{branch}[/bold]" if branch == current else branch
            console.print(f"  {marker}{display}")
        return

    if create_new:
        if name in lib.list_libraries():
            console.print(f"[red]Branch '{name}' already exists[/red]")
            return
        lib.create_library(name, orphan=empty)
        origin = "empty" if empty else f"forked from '{lib.current_library()}'"
        console.print(f"[green]Created branch '{name}' ({origin}) and switched to it[/green]")
    elif remove:
        if not yes:
            click.confirm(f"Delete branch '{name}'? This cannot be undone.", abort=True)
        try:
            lib.delete_library(name)
            console.print(f"[green]Deleted branch '{name}'[/green]")
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
    else:
        if name not in lib.list_libraries():
            console.print(f"[red]Branch '{name}' not found. Use 'skillm branch -n {name}' to create it.[/red]")
            return
        if reset and not yes:
            click.confirm(
                f"Reset '{name}' to remote/initial state? All local commits will be lost.",
                abort=True,
            )
        lib.switch_library(name, reset=reset)
        if reset:
            console.print(f"[green]Switched to branch '{name}' (reset to remote/initial state)[/green]")
        else:
            console.print(f"[green]Switched to branch '{name}'[/green]")


# ── Repo Management ────────────────────────────────────────

@cli.group()
def repo():
    """Manage skill repos (git clones)."""


@repo.command("add")
@click.argument("name")
@click.argument("url")
def repo_add(name: str, url: str):
    """Clone a remote URL as a named repo.

    \b
    URL can be anything git understands:
      https://oauth2:TOKEN@gitlab.com/team/skills.git   HTTPS with token
      git@github.com:team/skills.git                    SSH
      /shared/skills                                    Local path

    Tip: use 'git config --global credential.helper store'
    to avoid embedding tokens in URLs.
    """
    lib = _get_library()
    try:
        lib.add_repo(name, url)
        console.print(f"[green]Cloned repo '{name}' from {url}[/green]")
    except Exception as e:
        console.print(f"[red]{e}[/red]")


@repo.command("init")
@click.argument("name")
def repo_init(name: str):
    """Create a local-only repo (no remote)."""
    lib = _get_library()
    if lib.repo_mgr.repo_exists(name):
        console.print(f"[red]Repo '{name}' already exists[/red]")
        return
    lib.init_repo(name)
    console.print(f"[green]Created local repo '{name}'[/green]")


@repo.command("rm")
@click.argument("name")
@click.option("--yes", is_flag=True, help="Skip confirmation")
def repo_rm(name: str, yes: bool):
    """Remove a repo."""
    lib = _get_library()
    if not lib.repo_mgr.repo_exists(name):
        console.print(f"[red]Repo '{name}' not found[/red]")
        return
    if not yes:
        click.confirm(f"Delete repo '{name}'? This cannot be undone.", abort=True)
    try:
        lib.remove_repo(name)
        console.print(f"[green]Removed repo '{name}'[/green]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")


@repo.command("switch")
@click.argument("name")
def repo_switch(name: str):
    """Switch to a different repo."""
    lib = _get_library()
    try:
        lib.switch_repo(name)
        console.print(f"[green]Active repo: {name}[/green]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")


@repo.command("list")
def repo_list():
    """List all repos."""
    lib = _get_library()
    repos = lib.list_repos()
    active = lib.config.library.active_repo

    if not repos:
        console.print("[dim]No repos. Run: skillm repo init <name>[/dim]")
        return

    for info in repos:
        marker = " [green]← active[/green]" if info.name == active else ""
        url_str = f"  {info.url}" if info.url else "  (local)"
        console.print(f"  [bold]{info.name}[/bold]{url_str}{marker}")


# ── Push / Pull ───────────────────────────────────────────

@cli.command("push")
@click.argument("repo_name", required=False, default=None)
@click.option("-b", "--branch", "as_branch", default=None,
              help="Push to a different branch name on remote (creates it if needed)")
def push_cmd(repo_name: str | None, as_branch: str | None):
    """Push a repo to its origin.

    \b
    If REPO_NAME is omitted, pushes the active repo.

    Examples:
      skillm push                   Push active repo
      skillm push origin            Push named repo
      skillm push -b feat-review    Push to new remote branch
    """
    lib = _get_library()
    target = repo_name or lib.config.library.active_repo

    try:
        lib.push(repo_name, as_branch=as_branch)
        branch_info = f" → remote branch '{as_branch}'" if as_branch else ""
        console.print(f"[green]Pushed repo '{target}'{branch_info}[/green]")
    except Exception as e:
        msg = str(e)
        console.print(f"[red]Push failed: {msg}[/red]")
        if "protected" in msg.lower() or "denied" in msg.lower() or "rejected" in msg.lower():
            console.print("[dim]Tip: push to a new branch with: skillm push -b <branch-name>[/dim]")


@cli.command("pull")
@click.argument("repo_name", required=False, default=None)
@click.option("--branch", "branch_name", default=None, help="Fetch and checkout a specific branch")
def pull_cmd(repo_name: str | None, branch_name: str | None):
    """Pull from a repo's origin and rebuild the index.

    \b
    If REPO_NAME is omitted, pulls the active repo.
    Use --branch to fetch and checkout a specific remote branch.
    """
    lib = _get_library()
    target = repo_name or lib.config.library.active_repo

    try:
        if branch_name:
            backend = lib.repo_mgr.get_backend(target)
            git = backend.git

            # Fetch the specific branch
            git._run("fetch", "origin", f"{branch_name}:refs/remotes/origin/{branch_name}")

            # Create local branch if it doesn't exist
            if not git.branch_exists(branch_name):
                git._run("branch", "--track", branch_name, f"origin/{branch_name}")
                console.print(f"[green]Created library '{branch_name}' tracking origin/{branch_name}[/green]")

            git.switch_branch(branch_name)

            # Rebuild to index new tags
            count = lib.rebuild()
            console.print(f"[green]{count} version(s) indexed[/green]")
        else:
            count = lib.pull(repo_name)
            console.print(f"[green]Pulled repo '{target}' — {count} version(s) indexed[/green]")
    except Exception as e:
        console.print(f"[red]Pull failed: {e}[/red]")


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
    if skill.repo:
        console.print(f"[bold]Repo:[/bold] {skill.repo}")
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
@click.argument("name", required=False, default=None)
@click.option("--scan/--no-scan", default=True, help="Auto-scan content for undeclared requirements")
@_agent_option
@_root_option
def check_cmd(name: str | None, scan: bool, agent: str, project_root: str | None):
    """Check if skill requirements are met on this machine.

    \b
    Without arguments, checks all installed project skills.
    With a NAME argument, checks a single skill from the library.
    """
    from .check import check_requirements
    from .metadata import extract_metadata
    from .scan import scan_skill_content, diff_requires

    if name:
        # Single skill check from library
        lib = _get_library()
        skill = lib.info(name)
        if skill is None:
            console.print(f"[red]Skill '{name}' not found[/red]")
            return

        latest = lib.db.get_latest_version(skill.id)
        if latest is None:
            console.print(f"[red]No versions for '{name}'[/red]")
            return

        skill_dir = lib.get_skill_files_path(name, latest.version)
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
                if missing.env:
                    merged["env"] = list(set(merged.get("env", []) + missing.env))
                requires = merged

        console.print(f"[bold]{name}[/bold] environment check:")
        report = check_requirements(name, requires)
        _print_check_report(report)

        if scan:
            detected = scan_skill_content(meta.content)
            missing = diff_requires(meta.requires, detected)
            if missing.has_findings:
                console.print()
                console.print("  [dim]Auto-detected (not in frontmatter):[/dim]")
                if missing.bins:
                    console.print(f"    tools: {missing.bins}")
                if missing.env:
                    console.print(f"    env: {missing.env}")
    else:
        # Check all installed project skills
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
    except Exception as e:
        console.print(f"[red]Import failed: {e}[/red]")


if __name__ == "__main__":
    cli()
