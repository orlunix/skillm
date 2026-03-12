"""Environment verification for skills.

Checks whether a skill's requirements are met on the current machine:
- Binaries on PATH
- Python version
- Python packages
- Environment variables
- Platform (OS)
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CheckResult:
    """Result of a single requirement check."""
    ok: bool
    kind: str  # bins, python, packages, env, platform
    name: str
    message: str = ""


@dataclass
class SkillCheckReport:
    """Full check report for a skill."""
    skill_name: str
    results: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.ok)

    @property
    def all_ok(self) -> bool:
        return all(r.ok for r in self.results)

    @property
    def has_checks(self) -> bool:
        return len(self.results) > 0


def check_requirements(skill_name: str, requires: dict | list) -> SkillCheckReport:
    """Check all requirements for a skill.

    Args:
        skill_name: Name of the skill
        requires: Either a dict with structured requirements or a flat list of strings.
            Dict format:
                bins: [cmd1, cmd2]
                python: ">=3.10"
                packages: [httpx, click]
                env: [API_KEY, TOKEN]
                platform: [linux, macos]
            Flat list format (legacy):
                [python3, httpx, node]  — treated as bins
    """
    report = SkillCheckReport(skill_name=skill_name)

    if isinstance(requires, list):
        # Legacy flat list — treat as binaries
        reqs = {"bins": requires}
    elif isinstance(requires, dict):
        reqs = requires
    else:
        return report

    if "bins" in reqs:
        for bin_name in reqs["bins"]:
            report.results.append(_check_binary(str(bin_name)))

    if "python" in reqs:
        report.results.append(_check_python_version(str(reqs["python"])))

    if "packages" in reqs:
        for pkg in reqs["packages"]:
            report.results.append(_check_python_package(str(pkg)))

    if "env" in reqs:
        for var in reqs["env"]:
            report.results.append(_check_env_var(str(var)))

    if "platform" in reqs:
        platforms = reqs["platform"]
        if isinstance(platforms, str):
            platforms = [platforms]
        report.results.append(_check_platform(platforms))

    return report


def _check_binary(name: str) -> CheckResult:
    """Check if a binary is available on PATH."""
    # Handle version spec like "python3>=3.10"
    bin_name = name.split(">=")[0].split("<=")[0].split("==")[0].strip()

    path = shutil.which(bin_name)
    if path:
        # Try to get version
        version = _get_binary_version(bin_name)
        ver_str = f" ({version})" if version else ""
        return CheckResult(ok=True, kind="bins", name=bin_name,
                           message=f"Found at {path}{ver_str}")
    else:
        return CheckResult(ok=False, kind="bins", name=bin_name,
                           message=f"Not found on PATH")


def _check_python_version(spec: str) -> CheckResult:
    """Check Python version against a version spec like '>=3.10'."""
    current = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    if spec.startswith(">="):
        required = spec[2:]
        ok = _version_ge(current, required)
        if ok:
            return CheckResult(ok=True, kind="python", name=f"python{spec}",
                               message=f"Python {current}")
        else:
            return CheckResult(ok=False, kind="python", name=f"python{spec}",
                               message=f"Python {current} < {required}")
    elif spec.startswith("=="):
        required = spec[2:]
        ok = current.startswith(required)
        if ok:
            return CheckResult(ok=True, kind="python", name=f"python{spec}",
                               message=f"Python {current}")
        else:
            return CheckResult(ok=False, kind="python", name=f"python{spec}",
                               message=f"Python {current} != {required}")
    else:
        # Bare version like "3.10" — treat as >=
        ok = _version_ge(current, spec)
        return CheckResult(ok=ok, kind="python", name=f"python>={spec}",
                           message=f"Python {current}")


def _check_python_package(name: str) -> CheckResult:
    """Check if a Python package is installed."""
    # Handle version spec
    pkg_name = name.split(">=")[0].split("<=")[0].split("==")[0].strip()

    try:
        result = subprocess.run(
            [sys.executable, "-c", f"import importlib.metadata; print(importlib.metadata.version('{pkg_name}'))"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            return CheckResult(ok=True, kind="packages", name=pkg_name,
                               message=f"Installed ({version})")
        else:
            return CheckResult(ok=False, kind="packages", name=pkg_name,
                               message="Not installed")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return CheckResult(ok=False, kind="packages", name=pkg_name,
                           message="Could not check")


def _check_env_var(name: str) -> CheckResult:
    """Check if an environment variable is set."""
    value = os.environ.get(name)
    if value:
        # Show first few chars for confirmation, mask the rest
        preview = value[:4] + "..." if len(value) > 4 else value
        return CheckResult(ok=True, kind="env", name=name,
                           message=f"Set ({preview})")
    else:
        return CheckResult(ok=False, kind="env", name=name,
                           message="Not set")


def _check_platform(allowed: list[str]) -> CheckResult:
    """Check if current platform is in the allowed list."""
    current = sys.platform  # linux, darwin, win32
    # Normalize common names
    platform_map = {
        "linux": "linux",
        "macos": "darwin",
        "darwin": "darwin",
        "mac": "darwin",
        "windows": "win32",
        "win": "win32",
        "win32": "win32",
    }

    normalized = [platform_map.get(p.lower(), p.lower()) for p in allowed]
    friendly = {"linux": "Linux", "darwin": "macOS", "win32": "Windows"}.get(current, current)

    if current in normalized:
        return CheckResult(ok=True, kind="platform", name="platform",
                           message=f"{friendly}")
    else:
        allowed_str = ", ".join(allowed)
        return CheckResult(ok=False, kind="platform", name="platform",
                           message=f"{friendly} not in [{allowed_str}]")


def _get_binary_version(name: str) -> str:
    """Try to get version of a binary."""
    for flag in ["--version", "-V", "version"]:
        try:
            result = subprocess.run(
                [name, flag],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                # Take first line, truncate
                line = result.stdout.strip().split("\n")[0]
                return line[:60]
        except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError):
            continue
    return ""


def _version_ge(current: str, required: str) -> bool:
    """Check if current version >= required version."""
    def parse(v: str) -> tuple[int, ...]:
        parts = []
        for p in v.split("."):
            try:
                parts.append(int(p))
            except ValueError:
                break
        return tuple(parts)

    return parse(current) >= parse(required)
