"""Remote library management.

Stores named remotes (name → path) in ~/.skillm/remotes.toml.
Paths can be local (/path/to/lib) or SSH (ssh://user@host:/path).
One remote is active at a time — all commands operate on it.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_SKILLM_DIR = Path.home() / ".skillm"
REMOTES_FILE = "remotes.toml"

# Default remote created on first use
DEFAULT_REMOTE_NAME = "local"


@dataclass
class Remote:
    name: str
    path: str  # local path or ssh://user@host:/path

    @property
    def is_ssh(self) -> bool:
        return self.path.startswith("ssh://")

    def parse_ssh(self) -> tuple[str, str]:
        """Parse ssh://user@host:/path → (user@host, path).

        Raises ValueError if not an SSH remote.
        """
        if not self.is_ssh:
            raise ValueError(f"Not an SSH remote: {self.path}")

        rest = self.path[len("ssh://"):]
        if ":" not in rest:
            raise ValueError(f"Invalid SSH path (missing ':'): {self.path}")

        host_part, path_part = rest.split(":", 1)
        return host_part, path_part

    @property
    def local_path(self) -> Path:
        """Get local path. Raises ValueError if SSH remote."""
        if self.is_ssh:
            raise ValueError(f"Remote '{self.name}' is SSH, not local")
        return Path(self.path).expanduser()


@dataclass
class RemoteConfig:
    remotes: dict[str, Remote] = field(default_factory=dict)
    active: str = ""

    def get_active(self) -> Remote | None:
        if self.active and self.active in self.remotes:
            return self.remotes[self.active]
        return None


def _remotes_path() -> Path:
    return DEFAULT_SKILLM_DIR / REMOTES_FILE


def load_remotes() -> RemoteConfig:
    """Load remotes from ~/.skillm/remotes.toml."""
    path = _remotes_path()
    config = RemoteConfig()

    if not path.exists():
        # Create default local remote
        default = Remote(name=DEFAULT_REMOTE_NAME, path=str(DEFAULT_SKILLM_DIR))
        config.remotes[DEFAULT_REMOTE_NAME] = default
        config.active = DEFAULT_REMOTE_NAME
        save_remotes(config)
        return config

    with open(path, "rb") as f:
        data = tomllib.load(f)

    config.active = data.get("active", "")

    for name, info in data.get("remotes", {}).items():
        if isinstance(info, dict) and "path" in info:
            config.remotes[name] = Remote(name=name, path=info["path"])

    # Ensure there's always a default if none exists
    if not config.remotes:
        default = Remote(name=DEFAULT_REMOTE_NAME, path=str(DEFAULT_SKILLM_DIR))
        config.remotes[DEFAULT_REMOTE_NAME] = default
        config.active = DEFAULT_REMOTE_NAME

    if config.active not in config.remotes and config.remotes:
        config.active = next(iter(config.remotes))

    return config


def save_remotes(config: RemoteConfig) -> None:
    """Save remotes to ~/.skillm/remotes.toml."""
    path = _remotes_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [f'active = "{config.active}"', "", "[remotes]"]

    for name, remote in sorted(config.remotes.items()):
        lines.append(f"[remotes.{name}]")
        lines.append(f'path = "{remote.path}"')
        lines.append("")

    path.write_text("\n".join(lines) + "\n")


def add_remote(name: str, path: str) -> RemoteConfig:
    """Add a new remote."""
    config = load_remotes()
    config.remotes[name] = Remote(name=name, path=path)
    # First remote added becomes active
    if len(config.remotes) == 1 or not config.active:
        config.active = name
    save_remotes(config)
    return config


def remove_remote(name: str) -> RemoteConfig:
    """Remove a remote. Raises ValueError if not found or is the last one."""
    config = load_remotes()
    if name not in config.remotes:
        raise ValueError(f"Remote '{name}' not found")
    if len(config.remotes) <= 1:
        raise ValueError("Cannot remove the last remote")

    del config.remotes[name]
    if config.active == name:
        config.active = next(iter(config.remotes))
    save_remotes(config)
    return config


def switch_remote(name: str) -> RemoteConfig:
    """Switch active remote. Raises ValueError if not found."""
    config = load_remotes()
    if name not in config.remotes:
        raise ValueError(f"Remote '{name}' not found")
    config.active = name
    save_remotes(config)
    return config
