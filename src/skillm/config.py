"""Configuration loading and defaults."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_LIBRARY_PATH = Path.home() / ".skillm"
CONFIG_FILENAME = "config.toml"


@dataclass
class LibraryConfig:
    backend: str = "local"
    path: str = str(DEFAULT_LIBRARY_PATH)
    # SSH fields
    host: str = ""
    port: int = 22
    user: str = ""
    auth: str = "key"
    key_file: str = ""


@dataclass
class CacheConfig:
    enabled: bool = True
    path: str = str(DEFAULT_LIBRARY_PATH / "cache")
    ttl: int = 3600
    max_size: str = "500MB"


@dataclass
class Config:
    library: LibraryConfig = field(default_factory=LibraryConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)

    @property
    def library_path(self) -> Path:
        return Path(self.library.path).expanduser()


def load_config(config_path: Path | None = None) -> Config:
    """Load config from TOML file, falling back to defaults."""
    if config_path is None:
        config_path = DEFAULT_LIBRARY_PATH / CONFIG_FILENAME

    config = Config()

    if config_path.exists():
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        if "library" in data:
            for k, v in data["library"].items():
                if hasattr(config.library, k):
                    setattr(config.library, k, v)

        if "cache" in data:
            for k, v in data["cache"].items():
                if hasattr(config.cache, k):
                    setattr(config.cache, k, v)

    return config


def save_config(config: Config, config_path: Path | None = None) -> None:
    """Save config to TOML file."""
    if config_path is None:
        config_path = Path(config.library.path).expanduser() / CONFIG_FILENAME

    config_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "[library]",
        f'backend = "{config.library.backend}"',
        f'path = "{config.library.path}"',
    ]
    if config.library.backend == "ssh":
        lines.extend([
            f'host = "{config.library.host}"',
            f"port = {config.library.port}",
            f'user = "{config.library.user}"',
            f'auth = "{config.library.auth}"',
        ])
        if config.library.key_file:
            lines.append(f'key_file = "{config.library.key_file}"')

    lines.extend([
        "",
        "[cache]",
        f"enabled = {str(config.cache.enabled).lower()}",
        f'path = "{config.cache.path}"',
        f"ttl = {config.cache.ttl}",
        f'max_size = "{config.cache.max_size}"',
    ])

    config_path.write_text("\n".join(lines) + "\n")
