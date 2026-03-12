"""Auto-scan SKILL.md content to detect requirements.

Scans code blocks, inline code, and text patterns to suggest
binaries, packages, env vars, and platform hints that the skill
likely depends on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Known binary patterns ───────────────────────────────────

# command → binary name (if different)
KNOWN_BINS = {
    "python", "python3", "node", "npm", "npx", "bun", "deno",
    "go", "cargo", "rustc", "ruby", "gem", "java", "javac", "mvn", "gradle",
    "docker", "docker-compose", "podman",
    "git", "gh", "curl", "wget", "jq", "yq", "sed", "awk", "grep", "rg",
    "make", "cmake", "gcc", "g++", "clang",
    "ssh", "scp", "rsync",
    "kubectl", "helm", "terraform", "ansible",
    "ffmpeg", "imagemagick", "convert",
    "sqlite3", "psql", "mysql", "redis-cli", "mongosh",
    "pip", "pip3", "pipx", "uv", "poetry", "pdm",
    "brew", "apt", "apt-get", "yum", "dnf", "pacman",
    "tmux", "screen", "cam",
}

# ── Python package patterns ─────────────────────────────────

# import name → pip package name (when different)
IMPORT_TO_PACKAGE = {
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "sklearn": "scikit-learn",
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "gi": "PyGObject",
    "attr": "attrs",
    "lxml": "lxml",
    "selectolax": "selectolax",
}

# Packages in stdlib — don't suggest these
STDLIB_MODULES = {
    "os", "sys", "re", "json", "pathlib", "subprocess", "shutil",
    "hashlib", "datetime", "collections", "functools", "itertools",
    "typing", "abc", "io", "math", "random", "time", "logging",
    "argparse", "configparser", "csv", "sqlite3", "http", "urllib",
    "tempfile", "glob", "fnmatch", "copy", "enum", "dataclasses",
    "contextlib", "textwrap", "string", "struct", "socket", "ssl",
    "threading", "multiprocessing", "queue", "signal", "asyncio",
    "unittest", "pdb", "traceback", "warnings", "inspect", "dis",
    "importlib", "pkgutil", "zipfile", "tarfile", "gzip", "bz2",
    "xml", "html", "email", "base64", "binascii", "codecs",
    "platform", "sysconfig", "venv", "ensurepip",
}

# ── Env var patterns ────────────────────────────────────────

# Common env var patterns to look for
ENV_VAR_RE = re.compile(
    r'(?:'
    r'os\.environ\[[\"\'](\w+)[\"\']\]'        # os.environ["VAR"]
    r'|os\.environ\.get\([\"\'](\w+)[\"\']\)'   # os.environ.get("VAR")
    r'|os\.getenv\([\"\'](\w+)[\"\']\)'         # os.getenv("VAR")
    r'|process\.env\.(\w+)'                      # process.env.VAR (JS)
    r'|\$\{(\w+)\}'                              # ${VAR} in shell
    r'|\$([A-Z][A-Z0-9_]{2,})'                  # $VAR in shell (caps only)
    r'|ENV\[[\"\'](\w+)[\"\']\]'                 # ENV["VAR"] (Ruby)
    r')'
)

# Env vars to ignore (too common / not real deps)
IGNORE_ENV = {
    "HOME", "USER", "PATH", "PWD", "SHELL", "TERM", "LANG", "LC_ALL",
    "EDITOR", "VISUAL", "TMPDIR", "TMP", "TEMP", "HOSTNAME", "LOGNAME",
}


@dataclass
class ScanResult:
    """Detected requirements from content scanning."""
    bins: list[str] = field(default_factory=list)
    packages: list[str] = field(default_factory=list)
    env: list[str] = field(default_factory=list)

    @property
    def has_findings(self) -> bool:
        return bool(self.bins or self.packages or self.env)

    def to_requires(self) -> dict:
        """Convert to a requires dict."""
        result = {}
        if self.bins:
            result["bins"] = sorted(self.bins)
        if self.packages:
            result["packages"] = sorted(self.packages)
        if self.env:
            result["env"] = sorted(self.env)
        return result


def scan_skill_content(content: str) -> ScanResult:
    """Scan SKILL.md content to auto-detect requirements."""
    result = ScanResult()

    # Extract code blocks
    code_blocks = _extract_code_blocks(content)
    all_code = "\n".join(code_blocks)

    # Also scan the full content for inline patterns
    _scan_bins(content, all_code, result)
    _scan_python_imports(all_code, result)
    _scan_pip_installs(content, all_code, result)
    _scan_npm_installs(content, all_code, result)
    _scan_env_vars(content, all_code, result)

    # Deduplicate
    result.bins = sorted(set(result.bins))
    result.packages = sorted(set(result.packages))
    result.env = sorted(set(result.env))

    return result


def diff_requires(declared: dict | list, detected: ScanResult) -> ScanResult:
    """Find requirements detected but not declared.

    Returns a ScanResult with only the missing items.
    """
    if isinstance(declared, list):
        declared = {"bins": declared}

    declared_bins = set(declared.get("bins", []))
    declared_pkgs = set(declared.get("packages", []))
    declared_env = set(declared.get("env", []))

    missing = ScanResult()
    missing.bins = [b for b in detected.bins if b not in declared_bins]
    missing.packages = [p for p in detected.packages if p not in declared_pkgs]
    missing.env = [e for e in detected.env if e not in declared_env]

    return missing


def _extract_code_blocks(content: str) -> list[str]:
    """Extract all fenced code block contents."""
    blocks = []
    pattern = re.compile(r"```\w*\n(.*?)```", re.DOTALL)
    for match in pattern.finditer(content):
        blocks.append(match.group(1))
    return blocks


def _scan_bins(content: str, code: str, result: ScanResult) -> None:
    """Detect binary/CLI tool usage."""
    combined = content + "\n" + code

    for bin_name in KNOWN_BINS:
        # Match: start of line or after $ or after pipe, whitespace, then command
        patterns = [
            rf"(?:^|\$\s*|^\s*|\|\s*){re.escape(bin_name)}\s",  # shell usage
            rf"`{re.escape(bin_name)}\s",                         # inline code
            rf"`{re.escape(bin_name)}`",                          # backtick-wrapped
        ]
        for pat in patterns:
            if re.search(pat, combined, re.MULTILINE):
                # Skip pip/pip3 as bins — they're package managers, not deps
                if bin_name in ("pip", "pip3", "pipx", "uv", "poetry", "pdm",
                                "brew", "apt", "apt-get", "yum", "dnf", "pacman",
                                "gem", "npm", "npx"):
                    continue
                result.bins.append(bin_name)
                break


def _scan_python_imports(code: str, result: ScanResult) -> None:
    """Detect Python import statements."""
    # import X, from X import Y
    import_re = re.compile(r"^\s*(?:import|from)\s+(\w+)", re.MULTILINE)

    for match in import_re.finditer(code):
        module = match.group(1)
        if module in STDLIB_MODULES:
            continue

        # Map to pip package name
        pkg = IMPORT_TO_PACKAGE.get(module, module)
        result.packages.append(pkg)


def _scan_pip_installs(content: str, code: str, result: ScanResult) -> None:
    """Detect pip install commands."""
    combined = content + "\n" + code
    pip_re = re.compile(r"pip3?\s+install\s+([^\s\-][^\n]*)", re.MULTILINE)

    for match in pip_re.finditer(combined):
        pkgs = match.group(1).strip()
        for pkg in pkgs.split():
            # Skip flags
            if pkg.startswith("-"):
                continue
            # Strip version specs
            pkg_name = re.split(r"[>=<!\[]", pkg)[0]
            if pkg_name:
                result.packages.append(pkg_name)


def _scan_npm_installs(content: str, code: str, result: ScanResult) -> None:
    """Detect npm/bun install commands — adds 'node' as a bin dep."""
    combined = content + "\n" + code
    if re.search(r"(?:npm|bun|yarn|pnpm)\s+(?:install|add|i)\b", combined):
        if "node" not in result.bins:
            result.bins.append("node")


def _scan_env_vars(content: str, code: str, result: ScanResult) -> None:
    """Detect environment variable usage."""
    combined = content + "\n" + code

    for match in ENV_VAR_RE.finditer(combined):
        # Get the first non-None group
        var = next((g for g in match.groups() if g), None)
        if var and var not in IGNORE_ENV:
            result.env.append(var)
