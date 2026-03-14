"""Configuration loading and defaults.

New format: ~/.skillm/sources.toml replaces both config.toml and remotes.toml.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_SKILLM_DIR = Path.home() / ".skillm"
CONFIG_FILENAME = "sources.toml"

# Legacy filenames for migration
LEGACY_CONFIG = "config.toml"
LEGACY_REMOTES = "remotes.toml"


@dataclass
class Source:
    """A skill source (git repository)."""
    name: str = ""
    url: str = ""
    priority: int = 10

    @property
    def resolved_path(self) -> Path:
        """Resolve URL to a local path (expands ~ and resolves)."""
        return Path(self.url).expanduser().resolve()

    @property
    def is_remote(self) -> bool:
        """Check if this is a remote (non-local) source."""
        return self.url.startswith("ssh://") or self.url.startswith("git@")


@dataclass
class Settings:
    """Global skillm settings."""
    cache_dir: str = str(DEFAULT_SKILLM_DIR / "cache")
    default_source: str = ""


@dataclass
class Config:
    """Top-level configuration."""
    settings: Settings = field(default_factory=Settings)
    sources: list[Source] = field(default_factory=list)

    def get_source(self, name: str) -> Source | None:
        """Find a source by name."""
        for s in self.sources:
            if s.name == name:
                return s
        return None

    def get_default_source(self) -> Source | None:
        """Get the default source (explicit or highest priority)."""
        if self.settings.default_source:
            return self.get_source(self.settings.default_source)
        if self.sources:
            return min(self.sources, key=lambda s: s.priority)
        return None

    def source_names(self) -> list[str]:
        """List all source names."""
        return [s.name for s in self.sources]

    @property
    def cache_path(self) -> Path:
        return Path(self.settings.cache_dir).expanduser()


def load_config(config_path: Path | None = None) -> Config:
    """Load config from sources.toml, falling back to defaults."""
    if config_path is None:
        config_path = DEFAULT_SKILLM_DIR / CONFIG_FILENAME

    config = Config()

    if config_path.exists():
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        if "settings" in data:
            s = data["settings"]
            config.settings.cache_dir = s.get("cache_dir", config.settings.cache_dir)
            config.settings.default_source = s.get("default_source", "")

        for src_data in data.get("sources", []):
            config.sources.append(Source(
                name=src_data.get("name", ""),
                url=src_data.get("url", ""),
                priority=src_data.get("priority", 10),
            ))

    # Sort by priority
    config.sources.sort(key=lambda s: s.priority)

    return config


def save_config(config: Config, config_path: Path | None = None) -> None:
    """Save config to sources.toml."""
    if config_path is None:
        config_path = DEFAULT_SKILLM_DIR / CONFIG_FILENAME

    config_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "[settings]",
        f'cache_dir = "{config.settings.cache_dir}"',
        f'default_source = "{config.settings.default_source}"',
        "",
    ]

    for src in sorted(config.sources, key=lambda s: s.priority):
        lines.append("[[sources]]")
        lines.append(f'name = "{src.name}"')
        lines.append(f'url = "{src.url}"')
        lines.append(f"priority = {src.priority}")
        lines.append("")

    config_path.write_text("\n".join(lines) + "\n")


def migrate_config() -> Config | None:
    """Migrate from old config.toml + remotes.toml to sources.toml.

    Returns the new Config if migration happened, None if nothing to migrate.
    """
    new_path = DEFAULT_SKILLM_DIR / CONFIG_FILENAME
    if new_path.exists():
        return None  # Already migrated

    old_config_path = DEFAULT_SKILLM_DIR / LEGACY_CONFIG
    old_remotes_path = DEFAULT_SKILLM_DIR / LEGACY_REMOTES

    if not old_config_path.exists() and not old_remotes_path.exists():
        return None  # Nothing to migrate

    config = Config()

    # Migrate remotes → sources
    if old_remotes_path.exists():
        with open(old_remotes_path, "rb") as f:
            data = tomllib.load(f)

        active = data.get("active", "")
        priority = 10

        for name, info in data.get("remotes", {}).items():
            if isinstance(info, dict) and "path" in info:
                config.sources.append(Source(
                    name=name,
                    url=info["path"],
                    priority=priority,
                ))
                priority += 10

        if active:
            config.settings.default_source = active

    # If no remotes but old config exists, create a source from the library path
    if not config.sources and old_config_path.exists():
        with open(old_config_path, "rb") as f:
            data = tomllib.load(f)
        lib_data = data.get("library", {})
        path = lib_data.get("path", str(DEFAULT_SKILLM_DIR))
        config.sources.append(Source(
            name="local",
            url=path,
            priority=10,
        ))
        config.settings.default_source = "local"

    if config.sources:
        save_config(config)
        return config

    return None
