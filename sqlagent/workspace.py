from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import yaml


class WorkspaceError(RuntimeError):
    pass


class Workspace:
    """Filesystem skill workspace with small, auditable git operations."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def ensure_git(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if not (self.root / ".git").exists():
            self._git("init", "-b", "main")
            self._git("config", "user.email", "sqlagent@localhost")
            self._git("config", "user.name", "SQL Agent")

    def _git(self, *args: str, check: bool = True) -> str:
        result = subprocess.run(
            ["git", *args], cwd=self.root, text=True, capture_output=True, check=False
        )
        if check and result.returncode:
            raise WorkspaceError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()

    def write_text(self, relative: str, content: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def read_text(self, relative: str) -> str:
        return (self.root / relative).read_text(encoding="utf-8")

    def write_yaml(self, relative: str, value: Any) -> Path:
        return self.write_text(relative, yaml.safe_dump(value, allow_unicode=True, sort_keys=False))

    def read_yaml(self, relative: str, default: Any = None) -> Any:
        path = self.root / relative
        if not path.exists():
            return default
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def write_json(self, relative: str, value: Any) -> Path:
        return self.write_text(relative, json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    def commit(self, message: str) -> str:
        self.ensure_git()
        self._git("add", ".")
        if self._git("diff", "--cached", "--quiet", check=False) == "":
            # git diff --quiet has no stdout both when clean and when dirty; inspect status instead.
            status = self._git("status", "--porcelain")
            if not status:
                return self._git("rev-parse", "HEAD", check=False)
        self._git("commit", "-m", message)
        return self._git("rev-parse", "HEAD")

    def current_branch(self) -> str:
        self.ensure_git()
        return self._git("branch", "--show-current")

    def create_candidate(self, candidate_id: str) -> str:
        self.ensure_git()
        branch = f"evolution/{candidate_id}"
        self._git("checkout", "-b", branch)
        return branch

    def checkout(self, branch: str) -> None:
        self._git("checkout", branch)

    def branch_exists(self, branch: str) -> bool:
        return bool(self._git("show-ref", "--verify", f"refs/heads/{branch}", check=False))

    def promote(self, branch: str, tag: str, base: str = "main") -> None:
        self.checkout(base)
        self._git("merge", "--no-ff", branch, "-m", f"Promote {branch}")
        self._git("tag", "-f", tag)

    def files(self) -> list[str]:
        return sorted(
            str(path.relative_to(self.root))
            for path in self.root.rglob("*")
            if path.is_file() and ".git" not in path.parts
        )

