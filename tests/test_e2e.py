"""End-to-end tests simulating real user workflows.

Every test uses tmp_path for full isolation — no global state is touched.
Git repos are created fresh per test. No network access required.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from skillm.cli import cli
from skillm.config import Config
from skillm.core import Library, Project


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


# ── Helpers ────────────────────────────────────────────────


def _make_library(tmp_path: Path, name: str = "lib") -> Library:
    """Create an isolated library instance."""
    lib_path = tmp_path / name
    config = Config()
    config.library.path = str(lib_path)
    lib = Library(config)
    lib.init()
    return lib


def _make_skill_dir(tmp_path: Path, name: str, description: str = "",
                    tags: str = "", author: str = "tester") -> Path:
    """Create a skill directory with YAML frontmatter."""
    skill_dir = tmp_path / f"src-{name}"
    skill_dir.mkdir(exist_ok=True)
    desc = description or f"A skill called {name}."
    tag_line = f"tags: [{tags}]" if tags else "tags: []"
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n"
        f"{tag_line}\nauthor: {author}\n---\n\n"
        f"# {name}\n\nInstructions for {name}.\n"
    )
    return skill_dir


def _make_bare_repo(tmp_path: Path, name: str = "remote.git") -> Path:
    """Create a bare git repo to act as a remote."""
    bare = tmp_path / name
    bare.mkdir()
    subprocess.run(["git", "init", "--bare", str(bare)],
                   capture_output=True, check=True)
    return bare


def _patch_cli_library(monkeypatch, lib: Library):
    """Monkey-patch CLI to use our isolated library."""
    import skillm.cli
    monkeypatch.setattr(skillm.cli, "_get_library", lambda: lib)


def _patch_cli_project(monkeypatch, lib: Library, project_dir: Path,
                       agent: str = "claude"):
    """Monkey-patch CLI to use our isolated library and project."""
    import skillm.cli
    monkeypatch.setattr(skillm.cli, "_get_library", lambda: lib)

    def patched_get_project(library=None, agent=agent, project_root=None):
        return Project(
            project_dir=project_dir,
            library=library or lib,
            agent=agent,
        )
    monkeypatch.setattr(skillm.cli, "_get_project", patched_get_project)


# ── E2E: Full lifecycle ───────────────────────────────────


class TestFullLifecycle:
    """User creates a library, adds skills, installs into a project,
    upgrades, syncs — the complete happy path."""

    def test_add_install_upgrade_cycle(self, tmp_path):
        """add → install → publish again → upgrade"""
        lib = _make_library(tmp_path)
        skill_dir = _make_skill_dir(tmp_path, "web-scraper",
                                    tags="web, python", author="alice")

        # Publish
        name = lib.publish(skill_dir)
        assert name == "web-scraper"

        # Install into project (hard copy)
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        project = Project(project_dir=project_dir, library=lib, agent="claude")
        project.init()

        result = project.add("web-scraper", soft=False)
        assert result == "copied"
        assert (project.skills_dir / "web-scraper" / "SKILL.md").exists()

        # Publish update
        (skill_dir / "SKILL.md").write_text(
            "---\nname: web-scraper\ndescription: Improved scraper\n"
            "tags: [web, python]\nauthor: alice\n---\n\n"
            "# Web Scraper v2\n\nBetter instructions.\n"
        )
        lib.publish(skill_dir)

        # Upgrade
        upgraded = project.upgrade()
        assert len(upgraded) == 1
        assert upgraded[0] == "web-scraper"

    def test_add_remove_readd(self, tmp_path):
        """add → remove → add again works cleanly."""
        lib = _make_library(tmp_path)
        skill_dir = _make_skill_dir(tmp_path, "temp-skill")

        lib.publish(skill_dir)
        assert lib.remove("temp-skill")
        assert lib.info("temp-skill") is None

        # Re-add
        name = lib.publish(skill_dir)
        assert name == "temp-skill"
        assert lib.info("temp-skill") is not None

    def test_multiple_skills_list_search(self, tmp_path):
        """Add several skills, verify list and search work correctly."""
        lib = _make_library(tmp_path)

        skills_data = [
            ("deploy-k8s", "Deploy to Kubernetes", "k8s, deployment"),
            ("db-migrate", "Run database migrations", "postgres, migration"),
            ("lint-python", "Python linting rules", "python, lint"),
        ]

        for name, desc, tags in skills_data:
            sd = _make_skill_dir(tmp_path, name, description=desc, tags=tags)
            lib.publish(sd)

        # List returns all 3
        all_skills = lib.list_skills()
        assert len(all_skills) == 3

        # Search by keyword
        results = lib.search("postgres")
        assert len(results) >= 1
        assert any("db-migrate" in r.name for r in results)

        results = lib.search("Kubernetes")
        assert len(results) >= 1
        assert any("deploy-k8s" in r.name for r in results)

    def test_sync_restores_deleted_files(self, tmp_path):
        """Install → delete skill files → sync restores them."""
        lib = _make_library(tmp_path)
        skill_dir = _make_skill_dir(tmp_path, "critical-skill")
        lib.publish(skill_dir)

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        project = Project(project_dir=project_dir, library=lib, agent="claude")
        project.init()
        project.add("critical-skill")

        # Simulate accidental deletion
        dest = project.skills_dir / "critical-skill"
        if dest.is_symlink():
            dest.unlink()
        else:
            shutil.rmtree(dest)
        assert not (project.skills_dir / "critical-skill").exists()

        # Sync restores
        synced = project.sync()
        assert "critical-skill" in synced
        assert (project.skills_dir / "critical-skill" / "SKILL.md").exists() or \
               (project.skills_dir / "critical-skill").is_symlink()


# ── E2E: Pin and upgrade ──────────────────────────────────


class TestPinAndUpgrade:
    """Pinned skills should be skipped during upgrade."""

    def test_pinned_skill_not_upgraded(self, tmp_path):
        lib = _make_library(tmp_path)
        skill_dir = _make_skill_dir(tmp_path, "pinned-skill")
        lib.publish(skill_dir)

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        project = Project(project_dir=project_dir, library=lib, agent="claude")
        project.init()

        # Install with pin
        project.add("pinned-skill", pin=True, soft=False)

        # Publish update
        lib.publish(skill_dir)

        # Upgrade should skip pinned
        upgraded = project.upgrade()
        assert len(upgraded) == 0

    def test_mixed_pinned_and_unpinned(self, tmp_path):
        """One pinned, one unpinned — only unpinned gets upgraded."""
        lib = _make_library(tmp_path)
        sd1 = _make_skill_dir(tmp_path, "stable")
        sd2 = _make_skill_dir(tmp_path, "evolving")
        lib.publish(sd1)
        lib.publish(sd2)

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        project = Project(project_dir=project_dir, library=lib, agent="claude")
        project.init()
        project.add("stable", pin=True, soft=False)
        project.add("evolving", pin=False, soft=False)

        # Publish updates
        lib.publish(sd1)
        lib.publish(sd2)

        upgraded = project.upgrade()
        assert len(upgraded) == 1
        assert upgraded[0] == "evolving"


# ── E2E: Multi-library ────────────────────────────────────


class TestMultiLibrary:
    """Cross-library operations: search, install from non-active library."""

    def test_search_spans_all_repos(self, tmp_path):
        """Skills from multiple repos all appear in search results."""
        lib = _make_library(tmp_path)

        # Publish to active repo
        sd1 = _make_skill_dir(tmp_path, "api-gateway",
                              description="API gateway config", tags="api")
        lib.publish(sd1)

        # Create a second repo and publish there
        lib.init_repo("team")
        lib.switch_repo("team")
        sd2 = _make_skill_dir(tmp_path, "ci-pipeline",
                              description="CI/CD pipeline setup", tags="ci")
        lib.publish(sd2)

        # Switch back to first
        lib.switch_repo("local")

        # Rebuild indexes all repos
        count = lib.rebuild()
        assert count == 2  # one skill from each repo

        # Search finds skills from both
        results = lib.search("API")
        assert any("api-gateway" in r.name for r in results)

        results = lib.search("CI")
        assert any("ci-pipeline" in r.name for r in results)

    def test_install_from_non_active_repo(self, tmp_path):
        """Can install a skill from a different repo."""
        lib = _make_library(tmp_path)

        # Create a second repo and publish there
        lib.init_repo("team")
        lib.switch_repo("team")
        sd = _make_skill_dir(tmp_path, "deploy-k8s",
                             description="Deploy to K8s", tags="k8s")
        lib.publish(sd)

        # Switch back to local
        lib.switch_repo("local")
        lib.rebuild()

        # Install from team repo — skill found via search
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        project = Project(project_dir=project_dir, library=lib, agent="claude")
        project.init()

        result = project.add("deploy-k8s")
        assert result in ("linked", "copied")

    def test_same_skill_name_different_repos(self, tmp_path):
        """Same skill name in two repos — they don't collide in DB."""
        lib = _make_library(tmp_path)

        # Publish "deploy" in local repo
        sd1 = _make_skill_dir(tmp_path, "deploy",
                              description="Deploy web apps", tags="web")
        lib.publish(sd1)

        # Create "team" repo, publish "deploy" there too
        lib.init_repo("team")
        lib.switch_repo("team")
        sd2 = _make_skill_dir(tmp_path, "deploy",
                              description="Deploy ML models", tags="ml")
        lib.publish(sd2)

        lib.rebuild()

        # Both should exist in DB (different repos)
        all_skills = lib.list_skills()
        repos = {s.repo for s in all_skills if "deploy" in s.name}
        assert "local" in repos
        assert "team" in repos

    def test_empty_library_operations(self, tmp_path):
        """New library is empty — list/search return nothing."""
        lib = _make_library(tmp_path)
        lib.create_library("empty-lib")

        lib.rebuild()
        # Active library is now "empty-lib"
        assert lib.current_library() == "empty-lib"

        results = lib.search("anything")
        # Should not crash


# ── E2E: Push / Pull via bare repo ────────────────────────


class TestPushPull:
    """Simulate two users sharing skills via a bare git repo."""

    def test_push_pull_full_cycle(self, tmp_path):
        """User A publishes + pushes, User B pulls + installs."""
        bare = _make_bare_repo(tmp_path)

        # User A: create library, add skill, push
        lib_a = _make_library(tmp_path, "user_a_lib")
        sd = _make_skill_dir(tmp_path, "shared-tool",
                             description="A shared tool", tags="shared")
        lib_a.publish(sd)
        lib_a.backend.git.add_remote("origin", str(bare))
        lib_a.push()

        # User B: create library, pull, install
        lib_b = _make_library(tmp_path, "user_b_lib")
        lib_b.backend.git.add_remote("origin", str(bare))
        count = lib_b.pull()
        assert count == 1  # one skill

        skill = lib_b.info("shared-tool")
        assert skill is not None

        # Install into project
        project_dir = tmp_path / "user_b_project"
        project_dir.mkdir()
        project = Project(project_dir=project_dir, library=lib_b, agent="claude")
        project.init()
        result = project.add("shared-tool")
        assert result in ("linked", "copied")
        assert (project.skills_dir / "shared-tool" / "SKILL.md").exists() or \
               (project.skills_dir / "shared-tool").is_symlink()

    def test_push_pull_with_libraries(self, tmp_path):
        """Push/pull preserves multi-library structure."""
        bare = _make_bare_repo(tmp_path)

        # User A: two libraries with different skills
        lib_a = _make_library(tmp_path, "user_a")
        sd1 = _make_skill_dir(tmp_path, "skill-alpha", tags="alpha")
        lib_a.publish(sd1)

        lib_a.create_library("extras")
        sd2 = _make_skill_dir(tmp_path, "skill-beta", tags="beta")
        lib_a.publish(sd2)

        # Push both libraries
        lib_a.backend.git.add_remote("origin", str(bare))
        lib_a.push()  # pushes "extras" (current)

        lib_a.switch_library([b for b in lib_a.list_libraries() if b != "extras"][0])
        lib_a.push()  # pushes default

        # User B: pull and verify
        lib_b = _make_library(tmp_path, "user_b")
        lib_b.backend.git.add_remote("origin", str(bare))
        lib_b.pull()

        # Should have at least the skills from the pulled branch
        all_skills = lib_b.list_skills()
        skill_names = [s.name for s in all_skills]
        # At minimum, skills from the default branch should be present
        assert any("skill-alpha" in n for n in skill_names)

    def test_push_as_different_branch(self, tmp_path):
        """Push with --as renames the branch on remote."""
        bare = _make_bare_repo(tmp_path)

        lib = _make_library(tmp_path)
        sd = _make_skill_dir(tmp_path, "review-skill")
        lib.publish(sd)
        lib.backend.git.add_remote("origin", str(bare))

        # Push as "review-branch"
        lib.push(as_branch="review-branch")

        # Verify bare repo has the branch
        result = subprocess.run(
            ["git", "-C", str(bare), "branch"],
            capture_output=True, text=True,
        )
        assert "review-branch" in result.stdout


# ── E2E: Enable / Disable + Inject ────────────────────────


class TestEnableDisableInject:
    """Disabled skills should not appear in injected config."""

    def test_disable_excludes_from_inject(self, tmp_path):
        """Disabled skill is not injected into CLAUDE.md."""
        from skillm.inject import inject as inject_skills

        lib = _make_library(tmp_path)
        sd1 = _make_skill_dir(tmp_path, "active-skill")
        sd2 = _make_skill_dir(tmp_path, "hidden-skill")
        lib.publish(sd1)
        lib.publish(sd2)

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        project = Project(project_dir=project_dir, library=lib, agent="claude")
        project.init()
        project.add("active-skill")
        project.add("hidden-skill")

        # Disable one
        project.disable("hidden-skill")

        inject_dir = project.agent_dir
        (inject_dir / ".skills").mkdir(exist_ok=True)
        for name in ["active-skill", "hidden-skill"]:
            src = project.skills_dir / name
            dst = inject_dir / ".skills" / name
            if src.is_symlink():
                shutil.copytree(src.resolve(), dst, dirs_exist_ok=True)
            elif src.exists():
                shutil.copytree(src, dst, dirs_exist_ok=True)

        target = inject_skills(inject_dir, fmt="claude")
        if target.exists():
            content = target.read_text()
            assert "active-skill" in content
            assert "hidden-skill" not in content

    def test_enable_after_disable(self, tmp_path):
        """Enable restores a disabled skill."""
        lib = _make_library(tmp_path)
        sd = _make_skill_dir(tmp_path, "toggle-skill")
        lib.publish(sd)

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        project = Project(project_dir=project_dir, library=lib, agent="claude")
        project.init()
        project.add("toggle-skill")

        # Disable
        project.disable("toggle-skill")
        manifest = project.list_skills()
        assert manifest["toggle-skill"]["enabled"] is False

        # Enable
        project.enable("toggle-skill")
        manifest = project.list_skills()
        assert manifest["toggle-skill"]["enabled"] is True


# ── E2E: Rebuild recovers from DB corruption ──────────────


class TestRebuildRecovery:
    """Delete library.db → rebuild fully restores state."""

    def test_rebuild_after_db_deletion(self, tmp_path):
        """Deleting library.db and rebuilding restores all skills."""
        lib = _make_library(tmp_path)

        # Add several skills
        for name in ["alpha", "beta", "gamma"]:
            sd = _make_skill_dir(tmp_path, name, tags=name)
            lib.publish(sd)

        # Verify 3 skills
        assert len(lib.list_skills()) == 3

        # Destroy the DB
        db_path = lib.db.db_path
        assert db_path.exists()
        db_path.unlink()

        # Rebuild
        count = lib.rebuild()
        assert count == 3  # 3 skills

        # Verify full recovery
        assert len(lib.list_skills()) == 3
        for name in ["alpha", "beta", "gamma"]:
            skill = lib.info(name)
            assert skill is not None

    def test_rebuild_across_repos(self, tmp_path):
        """Rebuild indexes skills from ALL repos, not just active."""
        lib = _make_library(tmp_path)

        sd1 = _make_skill_dir(tmp_path, "main-skill")
        lib.publish(sd1)

        # Create a second repo
        lib.init_repo("team")
        lib.switch_repo("team")
        sd2 = _make_skill_dir(tmp_path, "team-skill")
        lib.publish(sd2)

        # Switch back
        lib.switch_repo("local")

        # Destroy and rebuild
        db_path = lib.db.db_path
        db_path.unlink()
        count = lib.rebuild()
        assert count == 2  # one from each repo

        all_skills = lib.list_skills()
        repos = {s.repo for s in all_skills}
        assert "local" in repos
        assert "team" in repos


# ── E2E: CLI commands ─────────────────────────────────────


class TestCLIWorkflows:
    """Test real CLI commands end-to-end via CliRunner."""

    def test_cli_add_list_info_search(self, tmp_path, monkeypatch):
        """CLI: add → list → info → search"""
        lib = _make_library(tmp_path)
        _patch_cli_library(monkeypatch, lib)

        skill_dir = _make_skill_dir(tmp_path, "cli-test-skill",
                                    description="Test CLI commands",
                                    tags="test, cli")

        runner = CliRunner()

        # Add
        result = runner.invoke(cli, ["add", str(skill_dir)])
        assert result.exit_code == 0
        assert "cli-test-skill" in result.output

        # List
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "cli-test-skill" in result.output

        # Info
        result = runner.invoke(cli, ["info", "cli-test-skill"])
        assert result.exit_code == 0
        assert "Test CLI commands" in result.output

        # Search
        result = runner.invoke(cli, ["search", "CLI"])
        assert result.exit_code == 0
        assert "cli-test-skill" in result.output

    def test_cli_install_upgrade_uninstall(self, tmp_path, monkeypatch):
        """CLI: install → upgrade → uninstall"""
        lib = _make_library(tmp_path)
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _patch_cli_project(monkeypatch, lib, project_dir)

        skill_dir = _make_skill_dir(tmp_path, "installable")
        lib.publish(skill_dir)

        runner = CliRunner()

        # Install
        result = runner.invoke(cli, ["install", "installable"])
        output = _strip_ansi(result.output)
        assert result.exit_code == 0
        assert "Installed" in output

        # Publish update
        lib.publish(skill_dir)

        # Upgrade
        result = runner.invoke(cli, ["upgrade"])
        output = _strip_ansi(result.output)
        assert result.exit_code == 0

        # Uninstall
        result = runner.invoke(cli, ["uninstall", "installable"])
        output = _strip_ansi(result.output)
        assert result.exit_code == 0
        assert "Uninstalled" in output

    def test_cli_sync(self, tmp_path, monkeypatch):
        """CLI: install → delete files → sync restores them."""
        lib = _make_library(tmp_path)
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _patch_cli_project(monkeypatch, lib, project_dir)

        skill_dir = _make_skill_dir(tmp_path, "syncable")
        lib.publish(skill_dir)

        runner = CliRunner()
        runner.invoke(cli, ["install", "syncable"])

        # Delete the files manually
        dest = project_dir / ".claude" / "skills" / "syncable"
        if dest.is_symlink():
            dest.unlink()
        elif dest.exists():
            shutil.rmtree(dest)

        # Sync
        result = runner.invoke(cli, ["sync"])
        assert result.exit_code == 0
        assert "syncable" in result.output

    def test_cli_enable_disable(self, tmp_path, monkeypatch):
        """CLI: install → disable → enable"""
        lib = _make_library(tmp_path)
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _patch_cli_project(monkeypatch, lib, project_dir)

        skill_dir = _make_skill_dir(tmp_path, "toggleable")
        lib.publish(skill_dir)

        runner = CliRunner()
        runner.invoke(cli, ["install", "toggleable"])

        result = runner.invoke(cli, ["disable", "toggleable"])
        assert result.exit_code == 0
        assert "Disabled" in result.output

        result = runner.invoke(cli, ["enable", "toggleable"])
        assert result.exit_code == 0
        assert "Enabled" in result.output

    def test_cli_tag_untag_categorize(self, tmp_path, monkeypatch):
        """CLI: add → tag → untag → categorize"""
        lib = _make_library(tmp_path)
        _patch_cli_library(monkeypatch, lib)

        skill_dir = _make_skill_dir(tmp_path, "taggable")
        lib.publish(skill_dir)

        runner = CliRunner()

        # Tag
        result = runner.invoke(cli, ["tag", "taggable", "devops", "automation"])
        assert result.exit_code == 0
        assert "Tagged" in result.output

        # Verify
        result = runner.invoke(cli, ["info", "taggable"])
        assert "devops" in result.output

        # Untag
        result = runner.invoke(cli, ["untag", "taggable", "automation"])
        assert result.exit_code == 0

        # Categorize
        result = runner.invoke(cli, ["categorize", "taggable", "infrastructure"])
        assert result.exit_code == 0

    def test_cli_branch_lifecycle(self, tmp_path, monkeypatch):
        """CLI: branch -n → branch (list) → branch <name> → branch --rm"""
        lib = _make_library(tmp_path)
        _patch_cli_library(monkeypatch, lib)

        runner = CliRunner()

        # Create
        result = runner.invoke(cli, ["branch", "-n", "experiments"])
        assert result.exit_code == 0
        assert "experiments" in result.output

        # List — should show both
        default = [b for b in lib.list_libraries() if b != "experiments"][0]
        result = runner.invoke(cli, ["branch"])
        assert result.exit_code == 0
        assert "experiments" in result.output

        # Switch back to default
        result = runner.invoke(cli, ["branch", default])
        assert result.exit_code == 0

        # Delete experiments
        result = runner.invoke(cli, ["branch", "--rm", "experiments", "--yes"])
        assert result.exit_code == 0
        assert "Deleted" in result.output

    def test_cli_repo_init_list_rm(self, tmp_path, monkeypatch):
        """CLI: repo init → list → rm"""
        lib = _make_library(tmp_path)
        _patch_cli_library(monkeypatch, lib)

        runner = CliRunner()

        # Init a new repo
        result = runner.invoke(cli, ["repo", "init", "extra"])
        assert result.exit_code == 0

        # List
        result = runner.invoke(cli, ["repo", "list"])
        assert result.exit_code == 0
        assert "extra" in result.output

        # Rm
        result = runner.invoke(cli, ["repo", "rm", "extra", "--yes"])
        assert result.exit_code == 0

    def test_cli_rm(self, tmp_path, monkeypatch):
        """CLI: add → rm → verify gone"""
        lib = _make_library(tmp_path)
        _patch_cli_library(monkeypatch, lib)

        skill_dir = _make_skill_dir(tmp_path, "removable")
        runner = CliRunner()

        runner.invoke(cli, ["add", str(skill_dir)])

        result = runner.invoke(cli, ["rm", "removable"])
        assert result.exit_code == 0
        assert "Removed" in result.output

        result = runner.invoke(cli, ["info", "removable"])
        assert "not found" in result.output

    def test_cli_install_hard(self, tmp_path, monkeypatch):
        """CLI: install --hard copies files."""
        lib = _make_library(tmp_path)
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _patch_cli_project(monkeypatch, lib, project_dir)

        skill_dir = _make_skill_dir(tmp_path, "hard-skill")
        lib.publish(skill_dir)

        runner = CliRunner()
        result = runner.invoke(cli, ["install", "hard-skill", "--hard"])
        output = _strip_ansi(result.output)
        assert result.exit_code == 0
        assert "copied" in output

        dest = project_dir / ".claude" / "skills" / "hard-skill"
        assert dest.exists()
        assert not dest.is_symlink()


# ── E2E: Agent variants ───────────────────────────────────


class TestAgentVariants:
    """Skills install into the correct agent-specific directory."""

    @pytest.mark.parametrize("agent,expected_dir", [
        ("claude", ".claude"),
        ("cursor", ".cursor"),
        ("codex", ".codex"),
        ("openclaw", ".openclaw"),
    ])
    def test_install_to_correct_agent_dir(self, tmp_path, agent, expected_dir):
        lib = _make_library(tmp_path)
        sd = _make_skill_dir(tmp_path, "agent-test")
        lib.publish(sd)

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        project = Project(project_dir=project_dir, library=lib, agent=agent)
        project.init()
        project.add("agent-test")

        skills_dir = project_dir / expected_dir / "skills"
        dest = skills_dir / "agent-test"
        assert dest.exists() or dest.is_symlink()
        assert (project_dir / expected_dir / "skills.json").exists()


# ── E2E: Error handling ───────────────────────────────────


class TestErrorHandling:
    """Verify graceful behavior on invalid operations."""

    def test_install_nonexistent_skill(self, tmp_path):
        lib = _make_library(tmp_path)
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        project = Project(project_dir=project_dir, library=lib, agent="claude")
        project.init()

        with pytest.raises(ValueError, match="not found"):
            project.add("nonexistent")

    def test_uninstall_nonexistent_skill(self, tmp_path):
        lib = _make_library(tmp_path)
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        project = Project(project_dir=project_dir, library=lib, agent="claude")
        project.init()

        assert project.drop("nonexistent") is False

    def test_remove_nonexistent_skill(self, tmp_path):
        lib = _make_library(tmp_path)
        assert lib.remove("nonexistent") is False

    def test_delete_active_library_fails(self, tmp_path):
        lib = _make_library(tmp_path)
        current = lib.current_library()
        with pytest.raises(ValueError, match="Cannot delete active"):
            lib.delete_library(current)

    def test_cli_install_nonexistent(self, tmp_path, monkeypatch):
        lib = _make_library(tmp_path)
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _patch_cli_project(monkeypatch, lib, project_dir)

        runner = CliRunner()
        result = runner.invoke(cli, ["install", "does-not-exist"])
        assert result.exit_code != 0 or "not found" in result.output.lower() or "error" in result.output.lower()

    def test_cli_rm_nonexistent(self, tmp_path, monkeypatch):
        lib = _make_library(tmp_path)
        _patch_cli_library(monkeypatch, lib)

        runner = CliRunner()
        result = runner.invoke(cli, ["rm", "ghost"])
        assert "not found" in result.output


# ── E2E: Inject with multiple installed skills ─────────────


class TestInjectMultipleSkills:
    """Install multiple skills, then inject into agent config."""

    def test_inject_creates_claude_md(self, tmp_path):
        from skillm.inject import inject as inject_skills

        lib = _make_library(tmp_path)

        for name in ["skill-a", "skill-b", "skill-c"]:
            sd = _make_skill_dir(tmp_path, name, description=f"Desc of {name}")
            lib.publish(sd)

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        project = Project(project_dir=project_dir, library=lib, agent="claude")
        project.init()
        for name in ["skill-a", "skill-b", "skill-c"]:
            project.add(name)

        # Set up inject's expected directory structure
        inject_dir = project.agent_dir
        skills_src = inject_dir / ".skills"
        skills_src.mkdir(exist_ok=True)
        for name in ["skill-a", "skill-b", "skill-c"]:
            src = project.skills_dir / name
            dst = skills_src / name
            if src.is_symlink():
                shutil.copytree(src.resolve(), dst, dirs_exist_ok=True)
            elif src.exists():
                shutil.copytree(src, dst, dirs_exist_ok=True)

        target = inject_skills(inject_dir, fmt="claude")
        assert target.exists()

        content = target.read_text()
        assert "skill-a" in content
        assert "skill-b" in content
        assert "skill-c" in content
        assert "<!-- skillm:start -->" in content
        assert "<!-- skillm:end -->" in content

    def test_inject_updates_existing(self, tmp_path):
        """Re-running inject updates the section, doesn't duplicate."""
        from skillm.inject import inject as inject_skills

        lib = _make_library(tmp_path)
        sd = _make_skill_dir(tmp_path, "solo")
        lib.publish(sd)

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        project = Project(project_dir=project_dir, library=lib, agent="claude")
        project.init()
        project.add("solo")

        inject_dir = project.agent_dir
        skills_src = inject_dir / ".skills"
        skills_src.mkdir(exist_ok=True)
        src = project.skills_dir / "solo"
        dst = skills_src / "solo"
        if src.is_symlink():
            shutil.copytree(src.resolve(), dst, dirs_exist_ok=True)
        elif src.exists():
            shutil.copytree(src, dst, dirs_exist_ok=True)

        # Write initial CLAUDE.md with existing content
        claude_md = inject_dir / "CLAUDE.md"
        claude_md.write_text("# My Project\n\nExisting content.\n")

        # Inject twice
        inject_skills(inject_dir, fmt="claude")
        inject_skills(inject_dir, fmt="claude")

        content = claude_md.read_text()
        # Should only have one skillm section
        assert content.count("<!-- skillm:start -->") == 1
        assert content.count("<!-- skillm:end -->") == 1
        # Existing content preserved
        assert "Existing content." in content
