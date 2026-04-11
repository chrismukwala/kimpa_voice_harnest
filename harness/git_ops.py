"""Git operations — auto-commit accepted changes."""

import logging
from typing import Optional

import git

log = logging.getLogger(__name__)


def is_git_repo(path: str) -> bool:
    """Return True if *path* is inside a git repository."""
    try:
        git.Repo(path, search_parent_directories=True)
        return True
    except (git.InvalidGitRepositoryError, git.NoSuchPathError):
        return False


def auto_commit(
    repo_path: str,
    file_path: str,
    message: Optional[str] = None,
) -> bool:
    """Stage *file_path* and commit with *message*.

    Returns True on success, False on failure.
    Never stages all files — only the specific file.
    """
    if message is None:
        message = f"Voice Harness: auto-commit {file_path}"

    try:
        repo = git.Repo(repo_path, search_parent_directories=True)
        repo.index.add([file_path])
        repo.index.commit(message)
        log.info("Auto-committed %s: %s", file_path, message)
        return True
    except (git.InvalidGitRepositoryError, git.NoSuchPathError, git.GitCommandError) as exc:
        log.warning("Git auto-commit failed for %s: %s", file_path, exc)
        return False
