"""Tests for harness/git_ops.py — auto-commit accepted changes."""

import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from harness.git_ops import auto_commit, is_git_repo


# =====================================================================
# is_git_repo
# =====================================================================

class TestIsGitRepo:
    """Detect whether a directory is inside a git repository."""

    def test_detects_git_repo(self, tmp_path):
        import subprocess
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        assert is_git_repo(str(tmp_path))

    def test_non_git_dir(self, tmp_path):
        assert not is_git_repo(str(tmp_path))


# =====================================================================
# auto_commit
# =====================================================================

class TestAutoCommit:
    """Verify auto-commit stages specific files and commits."""

    @patch("harness.git_ops.git.Repo")
    def test_stages_and_commits(self, MockRepo):
        mock_repo = MagicMock()
        MockRepo.return_value = mock_repo

        auto_commit(
            repo_path="/project",
            file_path="src/main.py",
            message="fix: update main function",
        )

        mock_repo.index.add.assert_called_once_with(["src/main.py"])
        mock_repo.index.commit.assert_called_once_with("fix: update main function")

    @patch("harness.git_ops.git.Repo")
    def test_uses_default_message(self, MockRepo):
        mock_repo = MagicMock()
        MockRepo.return_value = mock_repo

        auto_commit(repo_path="/project", file_path="test.py")

        call_args = mock_repo.index.commit.call_args
        assert "Voice Harness" in call_args[0][0]

    @patch("harness.git_ops.git.Repo")
    def test_does_not_stage_all(self, MockRepo):
        """Must never do git add . — only stage specific files."""
        mock_repo = MagicMock()
        MockRepo.return_value = mock_repo

        auto_commit(repo_path="/project", file_path="one.py")

        # index.add should be called with a list containing exactly one file
        args = mock_repo.index.add.call_args[0][0]
        assert args == ["one.py"]

    @patch("harness.git_ops.git.Repo")
    def test_handles_git_error_gracefully(self, MockRepo):
        import git
        MockRepo.side_effect = git.InvalidGitRepositoryError("not a repo")

        # Should not raise — returns False
        result = auto_commit(repo_path="/not-a-repo", file_path="f.py")
        assert result is False

    @patch("harness.git_ops.git.Repo")
    def test_returns_true_on_success(self, MockRepo):
        mock_repo = MagicMock()
        MockRepo.return_value = mock_repo

        result = auto_commit(repo_path="/project", file_path="f.py")
        assert result is True
