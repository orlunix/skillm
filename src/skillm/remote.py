"""Remote management for skillm.

Remotes are git remotes on the library's skills repo.
This module manages a thin config layer that tracks which
remote is the default push/pull target.

The actual URLs live in git config (via ``git remote``).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_SKILLM_DIR = Path.home() / ".skillm"
REMOTES_FILE = "remotes.toml"


@dataclass
class RemoteConfig:
    default: str = ""
    remotes: list[str] = field(default_factory=list)


def _remotes_path() -> Path:
    return DEFAULT_SKILLM_DIR / REMOTES_FILE


def load_remotes() -> RemoteConfig:
    """Load remote config from ~/.skillm/remotes.toml."""
    path = _remotes_path()
    if not path.exists():
        return RemoteConfig()

    with open(path, "rb") as f:
        data = tomllib.load(f)

    config = RemoteConfig()
    config.default = data.get("default", "")
    config.remotes = data.get("remotes", [])
    return config


def save_remotes(config: RemoteConfig) -> None:
    """Save remote config to ~/.skillm/remotes.toml."""
    path = _remotes_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    if config.default:
        lines.append(f'default = "{config.default}"')
    lines.append(f"remotes = {config.remotes}")
    lines.append("")

    path.write_text("\n".join(lines) + "\n")


def get_default_remote() -> str | None:
    """Get the default remote name, or None."""
    config = load_remotes()
    return config.default or None
