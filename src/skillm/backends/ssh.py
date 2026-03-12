"""SSH backend — operates on a remote library over SSH.

Uses subprocess calls to ssh/scp/rsync for simplicity.
The remote host must have the library directory accessible.

Write operations use flock on the remote to prevent concurrent
modifications from corrupting the database.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .base import LibraryBackend

# Timeout for acquiring the remote lock (seconds)
LOCK_TIMEOUT = 30
LOCK_FILENAME = ".skillm.lock"


class SSHBackend(LibraryBackend):
    """SSH-based remote library backend.

    Syncs the DB locally for reads, pushes changes back after writes.
    Skill files are transferred via rsync/scp.
    Write operations acquire a remote flock to prevent races.
    """

    def __init__(self, host: str, remote_path: str):
        self.host = host
        self.remote_path = remote_path.rstrip("/")
        self.remote_skills_dir = f"{self.remote_path}/skills"
        self.remote_db = f"{self.remote_path}/library.db"
        self.remote_lock = f"{self.remote_path}/{LOCK_FILENAME}"

        # Local cache dir for the DB
        self._cache_dir = Path(tempfile.mkdtemp(prefix="skillm-ssh-"))
        self._local_db = self._cache_dir / "library.db"

    def _ssh(self, cmd: str, check: bool = True, timeout: int = 30) -> subprocess.CompletedProcess:
        """Run a command on the remote host."""
        return subprocess.run(
            ["ssh", self.host, cmd],
            capture_output=True, text=True, timeout=timeout,
            check=check,
        )

    def _ssh_locked(self, cmd: str, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess:
        """Run a command on the remote host while holding the flock.

        Uses flock --timeout to wait up to LOCK_TIMEOUT seconds for the lock.
        If another process holds the lock, this will wait and retry.
        If the lock can't be acquired, flock exits with code 1.
        """
        locked_cmd = (
            f"flock --timeout {LOCK_TIMEOUT} {self.remote_lock} "
            f"sh -c {_shell_quote(cmd)}"
        )
        result = subprocess.run(
            ["ssh", self.host, locked_cmd],
            capture_output=True, text=True, timeout=timeout + LOCK_TIMEOUT,
            check=False,
        )
        if check and result.returncode != 0:
            if "flock" in result.stderr.lower() or result.returncode == 1:
                raise TimeoutError(
                    f"Could not acquire remote lock on {self.host}:{self.remote_lock} "
                    f"within {LOCK_TIMEOUT}s. Another operation may be in progress."
                )
            result.check_returncode()
        return result

    def _scp_get(self, remote: str, local: Path) -> None:
        """Copy a file from remote to local."""
        subprocess.run(
            ["scp", "-q", f"{self.host}:{remote}", str(local)],
            capture_output=True, check=True, timeout=60,
        )

    def _scp_put(self, local: Path, remote: str) -> None:
        """Copy a file from local to remote."""
        subprocess.run(
            ["scp", "-q", str(local), f"{self.host}:{remote}"],
            capture_output=True, check=True, timeout=60,
        )

    def _rsync_get(self, remote_dir: str, local_dir: Path) -> None:
        """Rsync a directory from remote to local."""
        local_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["rsync", "-az", "--delete",
             f"{self.host}:{remote_dir}/", f"{local_dir}/"],
            capture_output=True, check=True, timeout=120,
        )

    def _rsync_put(self, local_dir: Path, remote_dir: str) -> None:
        """Rsync a directory from local to remote."""
        self._ssh(f"mkdir -p {remote_dir}")
        subprocess.run(
            ["rsync", "-az", "--delete",
             f"{local_dir}/", f"{self.host}:{remote_dir}/"],
            capture_output=True, check=True, timeout=120,
        )

    @contextmanager
    def _remote_lock(self):
        """Context manager that holds a remote flock for the duration.

        Opens an SSH connection that holds flock, runs a sleep,
        and kills it on exit. This keeps the lock held for
        multi-step write operations (DB update + file upload).
        """
        proc = subprocess.Popen(
            ["ssh", self.host,
             f"flock --timeout {LOCK_TIMEOUT} {self.remote_lock} "
             f"sleep {LOCK_TIMEOUT + 60}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            # Give it a moment to acquire the lock
            try:
                proc.wait(timeout=LOCK_TIMEOUT + 2)
                # If it exited already, lock acquisition failed
                if proc.returncode != 0:
                    raise TimeoutError(
                        f"Could not acquire remote lock on {self.host}:{self.remote_lock}. "
                        f"Another operation may be in progress."
                    )
            except subprocess.TimeoutExpired:
                # Still running = lock is held. Good.
                pass
            yield
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    # ── Backend interface ──────────────────────────────────

    def initialize(self) -> None:
        """Create remote library directory structure."""
        self._ssh(f"mkdir -p {self.remote_path}/skills")

    def get_db(self) -> Path:
        """Download remote library.db to local cache (no lock needed for reads)."""
        result = self._ssh(f"test -f {self.remote_db}", check=False)
        if result.returncode == 0:
            self._scp_get(self.remote_db, self._local_db)
        return self._local_db

    def put_db(self, local_db: Path) -> None:
        """Upload local library.db to remote (caller must hold lock)."""
        self._scp_put(local_db, self.remote_db)

    def get_skill_files(self, name: str, version: str) -> Path:
        """Download skill files from remote (no lock needed for reads)."""
        remote = f"{self.remote_skills_dir}/{name}/{version}"
        local = self._cache_dir / "skills" / name / version
        self._rsync_get(remote, local)
        return local

    def put_skill_files(self, name: str, version: str, source_dir: Path) -> None:
        """Upload skill files and DB to remote, under lock."""
        with self._remote_lock():
            # Re-download DB to get latest state before writing
            result = self._ssh(f"test -f {self.remote_db}", check=False)
            if result.returncode == 0:
                self._scp_get(self.remote_db, self._local_db)

            remote = f"{self.remote_skills_dir}/{name}/{version}"
            self._rsync_put(source_dir, remote)

            if self._local_db.exists():
                self.put_db(self._local_db)

    def remove_skill_files(self, name: str, version: str | None = None) -> None:
        """Remove skill files on remote, under lock."""
        with self._remote_lock():
            if version:
                target = f"{self.remote_skills_dir}/{name}/{version}"
            else:
                target = f"{self.remote_skills_dir}/{name}"

            self._ssh(f"rm -rf {target}", check=False)

            if version:
                parent = f"{self.remote_skills_dir}/{name}"
                self._ssh(f"rmdir {parent} 2>/dev/null", check=False)

            if self._local_db.exists():
                self.put_db(self._local_db)

    def list_skill_dirs(self) -> list[tuple[str, list[str]]]:
        """List skills and versions on remote (no lock needed)."""
        result = self._ssh(
            f"find {self.remote_skills_dir} -mindepth 2 -maxdepth 2 -type d 2>/dev/null"
            f" | sort",
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []

        skills: dict[str, list[str]] = {}
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.replace(self.remote_skills_dir + "/", "").split("/")
            if len(parts) == 2:
                name, version = parts
                skills.setdefault(name, []).append(version)

        return [(name, sorted(versions)) for name, versions in sorted(skills.items())]

    def skill_exists(self, name: str, version: str) -> bool:
        """Check if skill version exists on remote (no lock needed)."""
        result = self._ssh(
            f"test -d {self.remote_skills_dir}/{name}/{version}",
            check=False,
        )
        return result.returncode == 0

    def cleanup(self) -> None:
        """Remove local cache directory."""
        if self._cache_dir.exists():
            shutil.rmtree(self._cache_dir)


def _shell_quote(s: str) -> str:
    """Quote a string for safe use in sh -c '...'."""
    return "'" + s.replace("'", "'\\''") + "'"
